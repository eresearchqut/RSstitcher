export interface ProcessParams {
  mode: "auto" | "symmetric" | "gid";
  scale: "linear" | "log" | "sqrt";
  phiTolerance: number;
  blurFraction: number;
  /** Beta cutoff in degrees. */
  beta: number;
  azimuthalBins: number | null;
  radialBins: [number, number][] | null;
  instrument: string;
  customInstrumentJson: string | null;
}

export interface InputFile {
  path: string;
  data: ArrayBuffer;
}

// Main -> Worker
export type WorkerMessage =
  | { type: "init" }
  | { type: "process"; files: InputFile[]; params: ProcessParams };

/** Progress payload carried by some log records (see web_entry.py). */
export interface ProcessProgress {
  stage: string;
  done: number;
  total: number;
  message: string;
}

/** One log record from a processing run. */
export interface ProcessLogRecord {
  /** Seconds since the run started. */
  elapsed: number;
  level: string;
  logger: string;
  message: string;
  progress: Omit<ProcessProgress, "message"> | null;
}

// Worker -> Main
export type WorkerResponse =
  | { type: "init-progress"; stage: string }
  | { type: "init-complete" }
  | { type: "process-log"; record: ProcessLogRecord }
  | {
      type: "process-complete";
      outputs: Record<string, ArrayBuffer>;
      summary: Record<string, unknown>;
      arrayData: ArrayBuffer;
      arrayShape: [number, number];
      gridData: ArrayBuffer;
    }
  | { type: "error"; error: string };

export type PyodideStatus =
  | "idle"
  | "loading"
  | "ready"
  | "processing"
  | "done"
  | "error";
