import { useState, useRef, useCallback, useEffect } from "react";
import { WorkerClient, type ProcessResult } from "../worker/workerClient";
import type { PyodideStatus, ProcessParams, InputFile } from "../worker/types";

export interface UsePyodideReturn {
  status: PyodideStatus;
  progressStage: string;
  error: string | null;
  result: ProcessResult | null;
  process: (files: InputFile[], params: ProcessParams) => Promise<void>;
}

export function usePyodide(): UsePyodideReturn {
  const [status, setStatus] = useState<PyodideStatus>("loading");
  const [progressStage, setProgressStage] = useState("");
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

      try {
        const processResult = await clientRef.current.process(files, params);
        setResult(processResult);
        setStatus("ready");
      } catch (e) {
        setError(String(e));
        setStatus("error");
      }
    },
    [],
  );

  return { status, progressStage, error, result, process };
}
