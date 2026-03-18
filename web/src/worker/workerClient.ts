import type {
  WorkerMessage,
  WorkerResponse,
  ProcessParams,
  InputFile,
} from "./types";

type ProgressCallback = (stage: string) => void;

export interface ProcessResult {
  outputs: Record<string, ArrayBuffer>;
  summary: Record<string, unknown>;
  arrayData: ArrayBuffer;
  arrayShape: [number, number];
  gridData: ArrayBuffer;
}

export class WorkerClient {
  private worker: Worker;
  private onProgress: ProgressCallback | null = null;

  constructor() {
    this.worker = new Worker(new URL("./pyodide.worker.ts", import.meta.url), {
      type: "module",
    });
  }

  async init(onProgress?: ProgressCallback): Promise<void> {
    this.onProgress = onProgress ?? null;

    return new Promise((resolve, reject) => {
      const handler = (event: MessageEvent<WorkerResponse>) => {
        const msg = event.data;
        switch (msg.type) {
          case "init-progress":
            this.onProgress?.(msg.stage);
            break;
          case "init-complete":
            this.worker.removeEventListener("message", handler);
            resolve();
            break;
          case "error":
            this.worker.removeEventListener("message", handler);
            reject(new Error(msg.error));
            break;
        }
      };
      this.worker.addEventListener("message", handler);
      this.send({ type: "init" });
    });
  }

  async process(
    files: InputFile[],
    params: ProcessParams,
  ): Promise<ProcessResult> {
    return new Promise((resolve, reject) => {
      const handler = (event: MessageEvent<WorkerResponse>) => {
        const msg = event.data;
        switch (msg.type) {
          case "process-complete":
            this.worker.removeEventListener("message", handler);
            resolve({
              outputs: msg.outputs,
              summary: msg.summary,
              arrayData: msg.arrayData,
              arrayShape: msg.arrayShape,
              gridData: msg.gridData,
            });
            break;
          case "error":
            this.worker.removeEventListener("message", handler);
            reject(new Error(msg.error));
            break;
        }
      };
      this.worker.addEventListener("message", handler);
      this.send({ type: "process", files, params });
    });
  }

  terminate() {
    this.worker.terminate();
  }

  private send(msg: WorkerMessage) {
    // Don't transfer input file buffers — they're held in React state
    // and need to survive for re-processing with different parameters
    this.worker.postMessage(msg);
  }
}
