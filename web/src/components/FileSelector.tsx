import { useState } from "react";
import type { UseFileSelectionReturn } from "../hooks/useFileSelection";
import { SAMPLE_DATASETS } from "../sampleDatasets";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const k = 1024;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

interface Props {
  fileSelection: UseFileSelectionReturn;
  disabled: boolean;
}

export function FileSelector({ fileSelection, disabled }: Props) {
  const {
    fileCount,
    totalSize,
    detectedFormat,
    selectDirectory,
    inputRef,
    handleChange,
    loadSampleDataset,
    sampleLoading,
    sampleProgress,
    sampleError,
  } = fileSelection;

  const [selectedSample, setSelectedSample] = useState("");

  const handleLoadSample = () => {
    const dataset = SAMPLE_DATASETS.find((d) => d.id === selectedSample);
    if (dataset) {
      loadSampleDataset(dataset);
    }
  };

  const isDisabled = disabled || sampleLoading;

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        // @ts-expect-error webkitdirectory is a non-standard attribute
        webkitdirectory=""
        multiple
        className="hidden"
        onChange={handleChange}
        disabled={isDisabled}
      />
      <button
        onClick={selectDirectory}
        disabled={isDisabled}
        className="rounded bg-blue-600 px-4 py-2 font-medium transition-colors hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500"
      >
        Select Directory
      </button>

      <div className="mt-3">
        <p className="mb-2 text-xs text-gray-500">Or try a sample dataset:</p>
        <div className="flex gap-2">
          <select
            value={selectedSample}
            onChange={(e) => setSelectedSample(e.target.value)}
            disabled={isDisabled}
            className="flex-1 rounded bg-gray-800 px-2 py-1.5 text-sm text-gray-300 disabled:text-gray-600"
          >
            <option value="">Choose...</option>
            {SAMPLE_DATASETS.map((d) => (
              <option key={d.id} value={d.id}>
                {d.name} ({d.sizeLabel})
              </option>
            ))}
          </select>
          <button
            onClick={handleLoadSample}
            disabled={isDisabled || !selectedSample}
            className="rounded bg-gray-700 px-3 py-1.5 text-sm font-medium transition-colors hover:bg-gray-600 disabled:text-gray-600"
          >
            Load
          </button>
        </div>
        {sampleLoading && sampleProgress && (
          <p className="mt-1 text-xs text-blue-400">
            Downloading... {sampleProgress.loaded}/{sampleProgress.total} files
          </p>
        )}
        {sampleError && (
          <p className="mt-1 text-xs text-red-400">{sampleError}</p>
        )}
      </div>

      {fileCount > 0 && (
        <div className="mt-3 space-y-1 text-sm text-gray-300">
          <p>
            <span className="text-gray-500">Files:</span> {fileCount}
          </p>
          <p>
            <span className="text-gray-500">Size:</span>{" "}
            {formatBytes(totalSize)}
          </p>
          {detectedFormat && (
            <p>
              <span className="text-gray-500">Format:</span> {detectedFormat}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
