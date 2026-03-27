/// <reference lib="webworker" />

import type { WorkerMessage, WorkerResponse, ProcessParams } from "./types";

// Import rsstitcher Python source as raw strings via Vite
import mainPy from "../../../rsstitcher/main.py?raw";
import initPy from "../../../rsstitcher/__init__.py?raw";
import webEntryPy from "../python/web_entry.py?raw";

// Pyodide types
interface PyodideInterface {
  loadPackage(packages: string[]): Promise<void>;
  FS: {
    mkdir(path: string): void;
    writeFile(path: string, data: string | Uint8Array): void;
    readFile(path: string): Uint8Array;
    analyzePath(path: string): { exists: boolean };
  };
  runPythonAsync(code: string): Promise<unknown>;
  globals: {
    get(name: string): unknown;
  };
}

let pyodide: PyodideInterface | null = null;

function post(msg: WorkerResponse) {
  self.postMessage(msg);
}

function mkdirp(fs: PyodideInterface["FS"], path: string) {
  const parts = path.split("/").filter(Boolean);
  let current = "";
  for (const part of parts) {
    current += "/" + part;
    if (!fs.analyzePath(current).exists) {
      fs.mkdir(current);
    }
  }
}

async function init() {
  try {
    post({ type: "init-progress", stage: "Loading Pyodide runtime..." });

    // Dynamic import works in ES module workers (importScripts does not)
    const { loadPyodide } = await import(
      // @ts-expect-error — CDN URL, no type declarations
      "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/pyodide.mjs"
    );
    pyodide = (await loadPyodide()) as PyodideInterface;

    post({
      type: "init-progress",
      stage: "Loading Python packages (numpy, pandas, scipy)...",
    });
    await pyodide.loadPackage(["numpy", "pandas", "scipy", "micropip"]);

    post({
      type: "init-progress",
      stage: "Installing tifffile and fabio...",
    });
    // Compute the app's base URL from the worker script location.
    // Worker URL is like .../assets/pyodide.worker-XXXX.js (prod) or .../src/worker/... (dev).
    // Walk up to the base path configured in vite (e.g. /RSstitcher/).
    const workerUrl = self.location.href;
    const origin = self.location.origin;
    // Strip origin, then keep everything up to and including the vite base path
    const pathname = new URL(workerUrl).pathname;
    // Find the base path: everything up to the first segment after origin
    // For /RSstitcher/assets/worker.js -> /RSstitcher/
    // For /RSstitcher/src/worker/... -> /RSstitcher/
    const segments = pathname.split("/").filter(Boolean);
    const baseUrl = segments.length > 1 ? `${origin}/${segments[0]}` : origin;

    await pyodide.runPythonAsync(`
import micropip
await micropip.install('tifffile')

# Install fabio from pre-built WASM wheel
from pyodide.http import pyfetch

# Read manifest to get exact wheel filename
response = await pyfetch('${baseUrl}/wheels/fabio-wheel.txt')
if response.ok:
    wheel_name = (await response.string()).strip()
    await micropip.install('${baseUrl}/wheels/' + wheel_name, deps=False)
else:
    # Fall back to PyPI (pure-Python only, no C extensions)
    await micropip.install('fabio', deps=False)
`);

    post({
      type: "init-progress",
      stage: "Setting up rsstitcher...",
    });

    // Write rsstitcher source to virtual FS
    mkdirp(pyodide.FS, "/rsstitcher/rsstitcher");
    pyodide.FS.writeFile("/rsstitcher/rsstitcher/__init__.py", initPy);
    pyodide.FS.writeFile("/rsstitcher/rsstitcher/main.py", mainPy);
    pyodide.FS.writeFile("/rsstitcher/web_entry.py", webEntryPy);

    // Import the web entry module
    await pyodide.runPythonAsync(`
import sys
sys.path.insert(0, '/rsstitcher')
sys.path.insert(0, '/rsstitcher')
import web_entry
`);

    post({ type: "init-complete" });
  } catch (e) {
    post({ type: "error", error: `Init failed: ${e}` });
  }
}

async function process(
  files: { path: string; data: ArrayBuffer }[],
  params: ProcessParams,
) {
  if (!pyodide) {
    post({ type: "error", error: "Pyodide not initialized" });
    return;
  }

  try {
    // Clean and create input/output directories
    await pyodide.runPythonAsync(`
import shutil, os
for d in ['/input', '/output']:
    if os.path.exists(d):
        shutil.rmtree(d)
    os.makedirs(d)
`);

    // Write input files to virtual FS, preserving directory structure
    for (const file of files) {
      const dir = file.path.substring(0, file.path.lastIndexOf("/"));
      if (dir) {
        mkdirp(pyodide.FS, `/input/${dir}`);
      }
      pyodide.FS.writeFile(`/input/${file.path}`, new Uint8Array(file.data));
    }

    // Build parameters for Python call
    const radialBinsStr =
      params.radialBins && params.radialBins.length > 0
        ? JSON.stringify(params.radialBins.map(([min, max]) => `${min},${max}`))
        : "None";

    const azBins =
      params.azimuthalBins !== null ? String(params.azimuthalBins) : "None";

    await pyodide.runPythonAsync(`
_result = web_entry.process(
    input_dir='/input',
    output_dir='/output',
    mode='${params.mode}',
    scale='${params.scale}',
    phi_tolerance=${params.phiTolerance},
    blur_fraction=${params.blurFraction},
    azimuthal_bins=${azBins},
    radial_bins_str=${radialBinsStr === "None" ? "None" : `'${radialBinsStr}'`},
)
`);

    // Read outputs from virtual FS
    // Use dict_converter to get plain JS objects instead of Maps
    const resultProxy = pyodide.globals.get("_result") as {
      toJs(options: {
        dict_converter: typeof Object.fromEntries;
      }): Record<string, unknown>;
    };
    const resultObj = resultProxy.toJs({ dict_converter: Object.fromEntries });

    const outputPaths = resultObj.outputs as Record<string, string>;
    const summaryObj = resultObj.summary as Record<string, unknown>;
    const arrayData = resultObj.array_data as Uint8Array;
    const arrayShape = resultObj.array_shape as number[];
    const gridData = resultObj.grid_data as Uint8Array;

    // Read output files from virtual FS
    const outputs: Record<string, ArrayBuffer> = {};
    for (const [key, path] of Object.entries(outputPaths)) {
      const data = pyodide.FS.readFile(path);
      outputs[key] = new Uint8Array(data).buffer as ArrayBuffer;
    }

    // Get array data as transferable buffers
    const arrayBuf = new Uint8Array(arrayData).buffer as ArrayBuffer;
    const gridBuf = new Uint8Array(gridData).buffer as ArrayBuffer;

    const response: WorkerResponse = {
      type: "process-complete",
      outputs,
      summary: summaryObj,
      arrayData: arrayBuf,
      arrayShape: arrayShape as [number, number],
      gridData: gridBuf,
    };

    // Transfer ArrayBuffers for zero-copy
    const transferables = [arrayBuf, gridBuf, ...Object.values(outputs)];
    self.postMessage(response, transferables as unknown as Transferable[]);
  } catch (e) {
    post({ type: "error", error: `Processing failed: ${e}` });
  }
}

self.onmessage = async (event: MessageEvent<WorkerMessage>) => {
  const msg = event.data;
  switch (msg.type) {
    case "init":
      await init();
      break;
    case "process":
      await process(msg.files, msg.params);
      break;
  }
};
