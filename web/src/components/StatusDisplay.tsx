import { useEffect, useRef } from "react";
import type {
  PyodideStatus,
  ProcessProgress,
  ProcessLogRecord,
} from "../worker/types";

interface Props {
  status: PyodideStatus;
  progressStage: string;
  processProgress: ProcessProgress | null;
  processLog: ProcessLogRecord[];
  error: string | null;
}

const LEVEL_CLASS: Record<string, string> = {
  DEBUG: "text-gray-500",
  INFO: "text-gray-300",
  WARNING: "text-yellow-400",
  ERROR: "text-red-400",
  CRITICAL: "text-red-400",
};

/** Collapsible log of the run, one line per record, kept scrolled to the end. */
function ProcessLog({ log }: { log: ProcessLogRecord[] }) {
  const preRef = useRef<HTMLPreElement>(null);
  useEffect(() => {
    const el = preRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [log.length]);

  return (
    <details className="group mt-2">
      <summary className="cursor-pointer list-none text-xs text-gray-500 hover:text-gray-300 [&::-webkit-details-marker]:hidden">
        <span className="inline-block w-3 transition-transform group-open:rotate-90">
          &#9656;
        </span>
        Processing log
      </summary>
      <pre
        ref={preRef}
        className="mt-1 max-h-56 overflow-auto rounded bg-gray-950 p-2 text-xs leading-relaxed"
      >
        {log.map((record, i) => (
          <div key={i} className={LEVEL_CLASS[record.level] ?? "text-gray-300"}>
            {record.elapsed.toFixed(2).padStart(7)} s {record.level.padEnd(7)}{" "}
            {record.message}
          </div>
        ))}
      </pre>
    </details>
  );
}

function renderWithLinks(text: string) {
  const parts = text.split(/(https?:\/\/[^\s]+)/g);
  return parts.map((part, i) =>
    /^https?:\/\//.test(part) ? (
      <a
        key={i}
        href={part}
        target="_blank"
        rel="noopener noreferrer"
        className="underline hover:text-red-300"
      >
        {part}
      </a>
    ) : (
      part
    ),
  );
}

export function StatusDisplay({
  status,
  progressStage,
  processProgress,
  processLog,
  error,
}: Props) {
  if (status === "idle") return null;

  return (
    <div className="text-sm">
      {status === "loading" && (
        <div className="flex items-center gap-2 text-yellow-400">
          <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-yellow-400 border-t-transparent" />
          {progressStage || "Initializing..."}
        </div>
      )}

      {status === "ready" && !error && (
        <span className="text-green-400">Ready to process</span>
      )}

      {status === "processing" && (
        <div className="text-yellow-400">
          <div className="flex items-center gap-2">
            <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-yellow-400 border-t-transparent" />
            {processProgress?.message ?? "Processing images..."}
          </div>
          {processProgress && processProgress.total > 1 && (
            <div
              className="mt-1.5 h-1 w-full max-w-md overflow-hidden rounded bg-gray-700"
              role="progressbar"
              aria-valuemin={0}
              aria-valuemax={processProgress.total}
              aria-valuenow={processProgress.done}
            >
              <div
                className="h-full bg-yellow-400 transition-[width] duration-100"
                style={{
                  width: `${(100 * processProgress.done) / processProgress.total}%`,
                }}
              />
            </div>
          )}
        </div>
      )}

      {status === "done" && (
        <span className="text-green-400">Processing complete</span>
      )}

      {error && (
        <div className="text-red-400">
          <p className="font-medium">Error</p>
          <pre className="mt-1 rounded bg-red-950/50 p-2 text-xs break-all whitespace-pre-wrap">
            {renderWithLinks(error)}
          </pre>
        </div>
      )}

      {processLog.length > 0 && <ProcessLog log={processLog} />}
    </div>
  );
}
