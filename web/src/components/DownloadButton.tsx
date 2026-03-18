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
      className="rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm transition-colors hover:bg-gray-700"
    >
      {label}
    </button>
  );
}
