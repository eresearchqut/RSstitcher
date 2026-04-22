import { useMemo, useState } from "react";
import type { ProcessParams } from "../worker/types";
import { OUTPUT_SUFFIXES } from "../outputUtils";

interface Props {
  params: ProcessParams;
  projectName: string;
}

const REPO_URL = "git+https://github.com/eresearchqut/RSstitcher";

/**
 * Shell-quote a value for a POSIX shell. Leaves safe values bare;
 * single-quotes anything with metacharacters (spaces, braces, globs, etc.).
 */
function shq(value: string): string {
  if (value === "") return "''";
  if (/^[A-Za-z0-9_\-./=:,]+$/.test(value)) return value;
  return "'" + value.replace(/'/g, "'\\''") + "'";
}

function buildCommand(params: ProcessParams, projectName: string): string {
  const lines: string[] = [
    `uvx --from ${REPO_URL} rsstitcher`,
    shq(projectName ? `./${projectName}` : "./input-directory"),
  ];

  lines.push(`--mode ${params.mode}`);
  lines.push(`--scale ${params.scale}`);
  lines.push(`--phi-tolerance ${params.phiTolerance}`);
  lines.push(`--blur-fraction ${params.blurFraction}`);
  if (params.azimuthalBins != null) {
    lines.push(`--azimuthal-bins ${params.azimuthalBins}`);
  }
  if (params.radialBins && params.radialBins.length > 0) {
    const pairs = params.radialBins.map(([min, max]) => `${min},${max}`);
    lines.push(`--radial-bins ${pairs.join(" ")}`);
  }
  if (params.instrument === "gfrm" || params.instrument === "img") {
    lines.push(`--instrument ${params.instrument}`);
  } else if (params.instrument === "custom") {
    lines.push(`--instrument-path ${shq("./instrument.json")}`);
  }

  const prefix = projectName.trim();
  const makePath = (suffix: string) =>
    prefix ? `${prefix}${suffix}` : suffix.slice(1);

  const writes: [string, string][] = [
    ["pixels_tiff", makePath(OUTPUT_SUFFIXES.pixels_tiff)],
    ["grid_tiff", makePath(OUTPUT_SUFFIXES.grid_tiff)],
    ["experiment_json", makePath(OUTPUT_SUFFIXES.experiment_json)],
  ];
  if (params.azimuthalBins != null) {
    writes.push(["azimuthal_csv", makePath(OUTPUT_SUFFIXES.azimuthal_csv)]);
  }
  if (params.radialBins && params.radialBins.length > 0) {
    writes.push(["radial_csv", makePath(OUTPUT_SUFFIXES.radial_csv)]);
  }
  for (const [key, path] of writes) {
    lines.push(`--write ${shq(`${key}=${path}`)}`);
  }

  return lines.join(" \\\n  ");
}

export function CLICommand({ params, projectName }: Props) {
  const command = useMemo(
    () => buildCommand(params, projectName),
    [params, projectName],
  );
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };

  return (
    <details className="group mt-4 rounded border border-gray-700 bg-gray-800/70 shadow-sm">
      <summary className="flex cursor-pointer list-none items-center gap-3 px-3 py-2.5 text-sm font-medium text-gray-200 hover:bg-gray-800 [&::-webkit-details-marker]:hidden">
        <svg
          className="h-4 w-4 shrink-0 text-gray-400 transition-transform duration-150 group-open:rotate-90"
          viewBox="0 0 20 20"
          fill="currentColor"
          aria-hidden="true"
        >
          <path
            fillRule="evenodd"
            d="M7.05 4.55a.75.75 0 011.06 0l4.9 4.9a.75.75 0 010 1.06l-4.9 4.9a.75.75 0 11-1.06-1.06L11.44 10 7.05 5.61a.75.75 0 010-1.06z"
            clipRule="evenodd"
          />
        </svg>
        <span className="flex-1">Equivalent CLI command</span>
        <span className="text-xs font-normal text-gray-500 group-open:hidden">
          click to expand
        </span>
        <span className="hidden text-xs font-normal text-gray-500 group-open:inline">
          Run locally with{" "}
          <a
            href="https://docs.astral.sh/uv/"
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="text-blue-400 hover:text-blue-300"
          >
            uv
          </a>
          . Replace the input path
          {params.instrument === "custom" && " and instrument JSON path"}.
        </span>
      </summary>
      <div className="border-t border-gray-700 p-3">
        <div className="relative">
          <pre className="overflow-x-auto rounded bg-gray-950 p-3 pr-20 text-xs whitespace-pre text-gray-200">
            <code className="whitespace-pre">{command}</code>
          </pre>
          <button
            onClick={handleCopy}
            className="absolute top-2 right-2 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-xs text-gray-300 hover:bg-gray-700"
          >
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
    </details>
  );
}
