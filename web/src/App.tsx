import { useState, useCallback } from "react";
import { usePyodide } from "./hooks/usePyodide";
import { useFileSelection } from "./hooks/useFileSelection";
import { FileSelector } from "./components/FileSelector";
import { ParameterControls } from "./components/ParameterControls";
import { StatusDisplay } from "./components/StatusDisplay";
import { OutputPanel } from "./components/OutputPanel";
import type { ProcessParams } from "./worker/types";

const DEFAULT_PARAMS: ProcessParams = {
  mode: "auto",
  scale: "linear",
  phiTolerance: 5.0,
  blurFraction: 0.1,
  azimuthalBins: null,
  radialBins: null,
  circles: null,
};

export default function App() {
  const pyodide = usePyodide();
  const fileSelection = useFileSelection();
  const [params, setParams] = useState<ProcessParams>(DEFAULT_PARAMS);

  const canProcess = pyodide.status === "ready" && fileSelection.fileCount > 0;

  const handleProcess = useCallback(async () => {
    if (!canProcess) return;
    await pyodide.process(fileSelection.files, params);
  }, [canProcess, pyodide, fileSelection.files, params]);

  const isWorking =
    pyodide.status === "loading" || pyodide.status === "processing";

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <header className="mb-8">
        <h1 className="text-2xl font-bold">RSstitcher</h1>
        <p className="mt-1 text-sm text-gray-400">
          Wide Range Reciprocal Space Map Builder — runs entirely in your
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

          <button
            onClick={handleProcess}
            disabled={!canProcess || isWorking}
            className="w-full rounded bg-green-600 px-4 py-2 font-medium transition-colors hover:bg-green-700 disabled:bg-gray-700 disabled:text-gray-500"
          >
            {pyodide.status === "processing" ? "Processing..." : "Process"}
          </button>
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
          <OutputPanel result={pyodide.result} />
        </div>
      )}
    </div>
  );
}
