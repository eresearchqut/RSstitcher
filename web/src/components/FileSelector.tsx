import type { UseFileSelectionReturn } from "../hooks/useFileSelection";

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
  } = fileSelection;

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
        disabled={disabled}
      />
      <button
        onClick={selectDirectory}
        disabled={disabled}
        className="rounded bg-blue-600 px-4 py-2 font-medium transition-colors hover:bg-blue-700 disabled:bg-gray-700 disabled:text-gray-500"
      >
        Select Directory
      </button>

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
