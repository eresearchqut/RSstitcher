import { useState, useCallback, useMemo } from "react";
import JSZip from "jszip";
import { usePyodide } from "./hooks/usePyodide";
import { useFileSelection } from "./hooks/useFileSelection";
import { FileSelector } from "./components/FileSelector";
import { ParameterControls } from "./components/ParameterControls";
import { StatusDisplay } from "./components/StatusDisplay";
import { OutputPanel } from "./components/OutputPanel";
import { OUTPUT_SUFFIXES, expandTemplate } from "./outputUtils";
import type { ProcessParams } from "./worker/types";

const DEFAULT_PARAMS: ProcessParams = {
  mode: "auto",
  scale: "linear",
  phiTolerance: 5.0,
  blurFraction: 0.1,
  azimuthalBins: 1,
  radialBins: [[0.1, 1.0]],
};

export default function App() {
  const pyodide = usePyodide();
  const [projectName, setProjectName] = useState("");
  const fileSelection = useFileSelection((dirName) => setProjectName(dirName));
  const [params, setParams] = useState<ProcessParams>(DEFAULT_PARAMS);

  const canProcess = pyodide.status === "ready" && fileSelection.fileCount > 0;

  const handleProcess = useCallback(async () => {
    if (!canProcess) return;
    await pyodide.process(fileSelection.files, params);
  }, [canProcess, pyodide, fileSelection.files, params]);

  const isWorking =
    pyodide.status === "loading" ||
    pyodide.status === "processing" ||
    fileSelection.sampleLoading;

  const zipFilenames = useMemo(() => {
    if (!pyodide.result) return {};
    const expanded = expandTemplate(projectName, pyodide.result.summary);
    const map: Record<string, string> = {};
    for (const [key, suffix] of Object.entries(OUTPUT_SUFFIXES)) {
      map[key] = expanded ? `${expanded}${suffix}` : suffix.slice(1);
    }
    return map;
  }, [projectName, pyodide.result]);

  const handleDownloadZip = useCallback(async () => {
    if (!pyodide.result) return;
    const zip = new JSZip();
    for (const [key, data] of Object.entries(pyodide.result.outputs)) {
      if (data && zipFilenames[key]) {
        zip.file(zipFilenames[key], data);
      }
    }
    const blob = await zip.generateAsync({ type: "blob" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    const expanded = expandTemplate(projectName, pyodide.result.summary);
    a.download = expanded ? `${expanded}.zip` : "rsstitcher.zip";
    a.click();
    URL.revokeObjectURL(url);
  }, [pyodide.result, zipFilenames, projectName]);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold">RSstitcher</h1>
          <a
            href="https://github.com/eresearchqut/RSstitcher"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 text-sm text-gray-400 transition-colors hover:text-gray-200"
          >
            <svg
              viewBox="0 0 16 16"
              width="16"
              height="16"
              fill="currentColor"
              aria-hidden="true"
            >
              <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
            </svg>
            github.com/eresearchqut/RSstitcher
          </a>
        </div>
        <p className="mt-1 text-sm text-gray-400">
          Wide Range Reciprocal Space Map builder running entirely in your
          browser
        </p>
      </header>

      <StatusDisplay
        status={pyodide.status}
        progressStage={pyodide.progressStage}
        error={pyodide.error}
      />

      <div className="mt-6 grid gap-6 md:grid-cols-[1fr_2fr]">
        <div className="space-y-4">
          <div>
            <h2 className="mb-2 text-sm font-medium text-gray-400">
              Input Data
            </h2>
            <FileSelector fileSelection={fileSelection} disabled={isWorking} />
          </div>

          <div>
            <label className="mb-1 block text-xs text-gray-500">
              Project name
            </label>
            <input
              type="text"
              value={projectName}
              onChange={(e) => setProjectName(e.target.value)}
              placeholder="project name"
              className="w-full rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-200 placeholder-gray-600 focus:border-gray-500 focus:outline-none"
            />
            <p className="mt-1 text-xs text-gray-600">
              Template vars: {"{type}"}, {"{mode}"}, {"{scale}"}, {"{delta_s}"},{" "}
              {"{wavelength_a}"}, {"{pixel_mm}"}, {"{detector_distance_mm}"},{" "}
              {"{phi0_deg}"}, {"{theta_pixel_rad}"}, {"{n_decimals}"},{" "}
              {"{blur_pixels}"}, {"{n_files}"}
            </p>
          </div>

          <button
            onClick={handleProcess}
            disabled={!canProcess || isWorking}
            className="w-full rounded bg-green-600 px-4 py-2 font-medium transition-colors hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500"
          >
            {pyodide.status === "processing" ? "Processing..." : "Process"}
          </button>

          {pyodide.result && (
            <button
              onClick={handleDownloadZip}
              className="w-full cursor-pointer rounded border border-gray-700 bg-gray-800 px-4 py-2 text-sm text-gray-300 transition-colors hover:bg-gray-700 hover:text-gray-100"
            >
              Download Results as ZIP
            </button>
          )}
        </div>

        <div>
          <h2 className="mb-2 text-sm font-medium text-gray-400">Parameters</h2>
          <ParameterControls
            params={params}
            onChange={setParams}
            disabled={isWorking}
          />
        </div>
      </div>

      {pyodide.result && (
        <div className="mt-8 border-t border-gray-800 pt-6">
          <OutputPanel result={pyodide.result} projectName={projectName} />
        </div>
      )}
    </div>
  );
}
