export interface ProcessParams {
  mode: "auto" | "symmetric" | "gid";
  scale: "linear" | "log" | "sqrt";
  phiTolerance: number;
  blurFraction: number;
  azimuthalBins: number | null;
  radialBins: [number, number][] | null;
  circles: number[] | null;
}

export interface InputFile {
  path: string;
  data: ArrayBuffer;
}

// Main -> Worker
export type WorkerMessage =
  | { type: "init" }
  | { type: "process"; files: InputFile[]; params: ProcessParams };

// Worker -> Main
export type WorkerResponse =
  | { type: "init-progress"; stage: string }
  | { type: "init-complete" }
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
