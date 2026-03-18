import type { PyodideStatus } from "../worker/types";

interface Props {
  status: PyodideStatus;
  progressStage: string;
  error: string | null;
}

export function StatusDisplay({ status, progressStage, error }: Props) {
  if (status === "idle") return null;

  return (
    <div className="text-sm">
      {status === "loading" && (
        <div className="flex items-center gap-2 text-yellow-400">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-yellow-400 border-t-transparent" />
          {progressStage || "Initializing..."}
        </div>
      )}

      {status === "ready" && (
        <span className="text-green-400">Ready to process</span>
      )}

      {status === "processing" && (
        <div className="flex items-center gap-2 text-yellow-400">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-yellow-400 border-t-transparent" />
          Processing images...
        </div>
      )}

      {status === "done" && (
        <span className="text-green-400">Processing complete</span>
      )}

      {status === "error" && error && (
        <div className="text-red-400">
          <p className="font-medium">Error</p>
          <pre className="mt-1 rounded bg-red-950/50 p-2 text-xs break-all whitespace-pre-wrap">
            {error}
          </pre>
        </div>
      )}
    </div>
  );
}
