interface Props {
  content: string;
  label: string;
}

export function TextPreview({ content, label }: Props) {
  return (
    <div>
      <h4 className="mb-1 text-sm font-medium text-gray-400">{label}</h4>
      <pre className="max-h-64 overflow-auto rounded border border-gray-800 bg-gray-900 p-3 text-xs whitespace-pre-wrap">
        {content}
      </pre>
    </div>
  );
}
