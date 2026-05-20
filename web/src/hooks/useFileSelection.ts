import { useState, useCallback, useRef } from "react";
import type { InputFile } from "../worker/types";
import { type SampleDataset, getSampleDatasetUrl } from "../sampleDatasets";

const VALID_EXTENSIONS = [".gfrm", ".img"];

export interface UseFileSelectionReturn {
  files: InputFile[];
  fileCount: number;
  totalSize: number;
  detectedFormat: string | null;
  selectDirectory: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  handleChange: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
  loadSampleDataset: (dataset: SampleDataset) => Promise<void>;
  clearFiles: () => void;
  sampleLoading: boolean;
  sampleProgress: { loaded: number; total: number } | null;
  sampleError: string | null;
}

export function useFileSelection(
  onDirectoryDetected?: (name: string) => void,
): UseFileSelectionReturn {
  const [files, setFiles] = useState<InputFile[]>([]);
  const [fileCount, setFileCount] = useState(0);
  const [totalSize, setTotalSize] = useState(0);
  const [detectedFormat, setDetectedFormat] = useState<string | null>(null);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [sampleProgress, setSampleProgress] = useState<{
    loaded: number;
    total: number;
  } | null>(null);
  const [sampleError, setSampleError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const selectDirectory = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const fileList = e.target.files;
      if (!fileList || fileList.length === 0) return;

      const validFiles: File[] = [];
      for (let i = 0; i < fileList.length; i++) {
        const file = fileList[i];
        const ext = file.name
          .substring(file.name.lastIndexOf("."))
          .toLowerCase();
        if (VALID_EXTENSIONS.includes(ext)) {
          validFiles.push(file);
        }
      }

      if (validFiles.length === 0) {
        setFiles([]);
        setFileCount(0);
        setTotalSize(0);
        setDetectedFormat(null);
        return;
      }

      // Extract the top-level directory name from the first file's path
      const firstPath = (validFiles[0] as File & { webkitRelativePath: string })
        .webkitRelativePath;
      const dirName = firstPath.split("/")[0];
      if (dirName) {
        onDirectoryDetected?.(dirName);
      }

      // Detect format from first file
      const firstExt = validFiles[0].name
        .substring(validFiles[0].name.lastIndexOf("."))
        .toLowerCase();
      setDetectedFormat(
        firstExt === ".gfrm" ? "Bruker (.gfrm)" : "Rigaku (.img)",
      );

      // Read all files as ArrayBuffers, preserving relative paths
      const inputFiles: InputFile[] = await Promise.all(
        validFiles.map(async (file) => {
          const data = await file.arrayBuffer();
          // webkitRelativePath gives "dirName/subdir/file.ext"
          // Strip the top-level directory name to get relative path
          const fullPath = (file as File & { webkitRelativePath: string })
            .webkitRelativePath;
          const parts = fullPath.split("/");
          // Remove the root directory selected by the user
          const relativePath = parts.slice(1).join("/");
          return { path: relativePath, data };
        }),
      );

      setFiles(inputFiles);
      setFileCount(inputFiles.length);
      setTotalSize(inputFiles.reduce((sum, f) => sum + f.data.byteLength, 0));
      setSampleError(null);
    },
    [onDirectoryDetected],
  );

  const clearFiles = useCallback(() => {
    setFiles([]);
    setFileCount(0);
    setTotalSize(0);
    setDetectedFormat(null);
    setSampleError(null);
  }, []);

  const loadSampleDataset = useCallback(
    async (dataset: SampleDataset) => {
      setSampleLoading(true);
      setSampleProgress({ loaded: 0, total: 0 });
      setSampleError(null);
      setFiles([]);
      setFileCount(0);
      setTotalSize(0);

      try {
        // Phase 1: HEAD each file in parallel to compute the total byte count.
        const sizes = await Promise.all(
          dataset.files.map(async (filePath) => {
            const url = getSampleDatasetUrl(dataset.id, filePath);
            const response = await fetch(url, { method: "HEAD" });
            if (!response.ok) {
              throw new Error(`Failed to HEAD ${filePath}: ${response.status}`);
            }
            const len = response.headers.get("Content-Length");
            return len ? parseInt(len, 10) : 0;
          }),
        );
        const total = sizes.reduce((a, b) => a + b, 0);
        setSampleProgress({ loaded: 0, total });

        // Phase 2: Stream each file in parallel, batching UI updates via rAF
        // so thousands of chunk callbacks across parallel downloads don't
        // thrash React renders.
        let loaded = 0;
        let rafPending = false;
        const scheduleProgressUpdate = () => {
          if (rafPending) return;
          rafPending = true;
          requestAnimationFrame(() => {
            rafPending = false;
            setSampleProgress({ loaded, total });
          });
        };

        const inputFiles = await Promise.all(
          dataset.files.map(async (filePath) => {
            const url = getSampleDatasetUrl(dataset.id, filePath);
            const response = await fetch(url);
            if (!response.ok) {
              throw new Error(
                `Failed to fetch ${filePath}: ${response.status}`,
              );
            }
            if (!response.body) {
              const data = await response.arrayBuffer();
              loaded += data.byteLength;
              scheduleProgressUpdate();
              return { path: filePath, data };
            }
            const reader = response.body.getReader();
            const chunks: Uint8Array[] = [];
            let received = 0;
            while (true) {
              const { done, value } = await reader.read();
              if (done) break;
              chunks.push(value);
              received += value.byteLength;
              loaded += value.byteLength;
              scheduleProgressUpdate();
            }
            const data = new ArrayBuffer(received);
            const view = new Uint8Array(data);
            let offset = 0;
            for (const chunk of chunks) {
              view.set(chunk, offset);
              offset += chunk.byteLength;
            }
            return { path: filePath, data };
          }),
        );
        setSampleProgress({ loaded, total });

        setFiles(inputFiles);
        setFileCount(inputFiles.length);
        setTotalSize(inputFiles.reduce((sum, f) => sum + f.data.byteLength, 0));
        setDetectedFormat(dataset.format);
        onDirectoryDetected?.(dataset.id);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : "Download failed";
        setSampleError(message);
        setFiles([]);
        setFileCount(0);
        setTotalSize(0);
        setDetectedFormat(null);
      } finally {
        setSampleLoading(false);
        setSampleProgress(null);
      }
    },
    [onDirectoryDetected],
  );

  return {
    files,
    fileCount,
    totalSize,
    detectedFormat,
    selectDirectory,
    inputRef,
    handleChange,
    loadSampleDataset,
    clearFiles,
    sampleLoading,
    sampleProgress,
    sampleError,
  };
}
