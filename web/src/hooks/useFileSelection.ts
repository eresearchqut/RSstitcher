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

  const loadSampleDataset = useCallback(
    async (dataset: SampleDataset) => {
      setSampleLoading(true);
      setSampleProgress({ loaded: 0, total: dataset.files.length });
      setSampleError(null);
      setFiles([]);
      setFileCount(0);
      setTotalSize(0);

      try {
        let loaded = 0;
        const inputFiles = await Promise.all(
          dataset.files.map(async (filePath) => {
            const url = getSampleDatasetUrl(dataset.id, filePath);
            const response = await fetch(url);
            if (!response.ok) {
              throw new Error(
                `Failed to fetch ${filePath}: ${response.status}`,
              );
            }
            const data = await response.arrayBuffer();
            loaded++;
            setSampleProgress({ loaded, total: dataset.files.length });
            return { path: filePath, data };
          }),
        );

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
    sampleLoading,
    sampleProgress,
    sampleError,
  };
}
