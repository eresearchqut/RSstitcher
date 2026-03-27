interface Props {
  data: ArrayBuffer;
  filename: string;
  label: string;
}

export function DownloadButton({ data, filename, label }: Props) {
  const handleClick = () => {
    const blob = new Blob([data]);
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <button
      onClick={handleClick}
      className="cursor-pointer rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm text-gray-300 transition-colors hover:bg-gray-700 hover:text-gray-100"
    >
      Download {label}
    </button>
  );
}
