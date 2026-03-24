import { useState, useCallback, useRef } from "react";
import type { InputFile } from "../worker/types";

const VALID_EXTENSIONS = [".gfrm", ".img"];

export interface UseFileSelectionReturn {
  files: InputFile[];
  fileCount: number;
  totalSize: number;
  detectedFormat: string | null;
  selectDirectory: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  handleChange: (e: React.ChangeEvent<HTMLInputElement>) => Promise<void>;
}

export function useFileSelection(
  onDirectoryDetected?: (name: string) => void,
): UseFileSelectionReturn {
  const [files, setFiles] = useState<InputFile[]>([]);
  const [fileCount, setFileCount] = useState(0);
  const [totalSize, setTotalSize] = useState(0);
  const [detectedFormat, setDetectedFormat] = useState<string | null>(null);
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
  };
}
