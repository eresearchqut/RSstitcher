import { useState, useRef, useCallback, useEffect } from "react";
import { WorkerClient, type ProcessResult } from "../worker/workerClient";
import type {
  PyodideStatus,
  ProcessParams,
  ProcessProgress,
  ProcessLogRecord,
  InputFile,
} from "../worker/types";

export interface UsePyodideReturn {
  status: PyodideStatus;
  progressStage: string;
  processProgress: ProcessProgress | null;
  /** Log of the current or most recent processing run. */
  processLog: ProcessLogRecord[];
  error: string | null;
  result: ProcessResult | null;
  process: (files: InputFile[], params: ProcessParams) => Promise<void>;
}

export function usePyodide(): UsePyodideReturn {
  const [status, setStatus] = useState<PyodideStatus>("loading");
  const [progressStage, setProgressStage] = useState("");
  const [processProgress, setProcessProgress] =
    useState<ProcessProgress | null>(null);
  const [processLog, setProcessLog] = useState<ProcessLogRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessResult | null>(null);
  const clientRef = useRef<WorkerClient | null>(null);

  // Auto-init on mount
  useEffect(() => {
    const client = new WorkerClient();
    clientRef.current = client;

    client
      .init((stage) => setProgressStage(stage))
      .then(() => setStatus("ready"))
      .catch((e) => {
        setError(String(e));
        setStatus("error");
      });
  }, []);

  const process = useCallback(
    async (files: InputFile[], params: ProcessParams) => {
      if (!clientRef.current) {
        setError("Pyodide not initialized");
        setStatus("error");
        return;
      }

      setStatus("processing");
      setError(null);
      setResult(null);
      setProcessProgress(null);
      setProcessLog([]);

      try {
        const processResult = await clientRef.current.process(
          files,
          params,
          (record) => {
            setProcessLog((log) => [...log, record]);
            if (record.progress) {
              setProcessProgress({
                ...record.progress,
                message: record.message,
              });
            }
          },
        );
        setResult(processResult);
        setStatus("ready");
      } catch (e) {
        setError(String(e));
        setStatus("ready");
      } finally {
        setProcessProgress(null);
      }
    },
    [],
  );

  return {
    status,
    progressStage,
    processProgress,
    processLog,
    error,
    result,
    process,
  };
}
