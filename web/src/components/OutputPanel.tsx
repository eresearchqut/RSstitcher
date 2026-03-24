import { useMemo } from "react";
import type { ProcessResult } from "../worker/workerClient";
import { ImagePreview } from "./ImagePreview";
import { DownloadButton } from "./DownloadButton";

interface Props {
  result: ProcessResult;
  projectName: string;
  onProjectNameChange: (name: string) => void;
}

const PARAM_LABELS: Record<string, string> = {
  type: "Format",
  mode: "Mode",
  data_size: "Data size",
  detector_distance_mm: "Detector distance",
  phi0_deg: "Phi 0",
  wavelength_a: "Wavelength",
  pixel_mm: "Pixel size",
  theta_pixel_rad: "Theta pixel",
  delta_s: "Delta s",
  n_decimals: "Rounding",
  blur_pixels: "Blur",
  scale: "Scale",
  sx_range: "Sx range",
  sz_range: "Sz range",
  result_shape: "Output size",
  n_files: "Files processed",
};

function formatValue(key: string, value: unknown): string {
  if (key === "data_size" || key === "result_shape") {
    const arr = value as number[];
    return `${arr[0]} x ${arr[1]} px`;
  }
  if (key === "sx_range" || key === "sz_range") {
    const arr = value as number[];
    return `${arr[0].toFixed(3)} to ${arr[1].toFixed(3)} A\u207B\u00B9`;
  }
  if (key === "detector_distance_mm") return `${value} mm`;
  if (key === "phi0_deg") return `${value}\u00B0`;
  if (key === "wavelength_a") return `${value} \u00C5`;
  if (key === "pixel_mm") return `${value} mm`;
  if (key === "theta_pixel_rad") {
    const deg = (value as number) * (180 / Math.PI);
    return `${deg.toFixed(3)}\u00B0`;
  }
  if (key === "delta_s") return `${value} \u00C5\u207B\u00B9`;
  if (key === "n_decimals") return `${value} decimal places`;
  if (key === "blur_pixels") return `${value} px`;
  return String(value);
}

const OUTPUT_SUFFIXES: Record<string, string> = {
  pixels_tiff: "_pixels.tiff",
  grid_tiff: "_grid.tiff",
  experiment_json: "_experiment.json",
  azimuthal_csv: "_1D.csv",
  radial_csv: "_debeye_ring_profile.csv",
};

const OUTPUT_LABELS: Record<string, string> = {
  pixels_tiff: "Pixels TIFF",
  grid_tiff: "Grid TIFF",
  experiment_json: "Experiment JSON",
  azimuthal_csv: "Azimuthal CSV",
  radial_csv: "Radial CSV",
};

/**
 * Expand Python-style `{variable}` templates using experiment summary values.
 * Unknown variables are left as-is.
 */
function expandTemplate(
  template: string,
  vars: Record<string, unknown>,
): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) => {
    const val = vars[key];
    return val !== undefined ? String(val) : match;
  });
}

export function OutputPanel({
  result,
  projectName,
  onProjectNameChange,
}: Props) {
  const filenames = useMemo(() => {
    const expanded = expandTemplate(projectName, result.summary);
    const map: Record<string, string> = {};
    for (const [key, suffix] of Object.entries(OUTPUT_SUFFIXES)) {
      map[key] = expanded ? `${expanded}${suffix}` : suffix.slice(1);
    }
    return map;
  }, [projectName, result.summary]);

  return (
    <div className="space-y-6">
      {/* Preview */}
      <ImagePreview
        arrayData={result.arrayData}
        arrayShape={result.arrayShape}
        gridData={result.gridData}
      />

      {/* Experiment parameters */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-400">
          Experiment Parameters
        </h3>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm sm:grid-cols-3">
          {Object.entries(PARAM_LABELS).map(([key, label]) => {
            const value = result.summary[key];
            if (value === undefined) return null;
            return (
              <div key={key} className="flex justify-between gap-2">
                <dt className="text-gray-500">{label}</dt>
                <dd className="text-right text-gray-200 tabular-nums">
                  {formatValue(key, value)}
                </dd>
              </div>
            );
          })}
        </dl>
      </div>

      {/* Downloads */}
      <div>
        <h3 className="mb-2 text-sm font-medium text-gray-400">Downloads</h3>
        <div className="mb-3">
          <label className="mb-1 block text-xs text-gray-500">
            Project name{" "}
            <span className="text-gray-600">
              (template vars: {"{delta_s}"}, {"{mode}"}, {"{scale}"}, ...)
            </span>
          </label>
          <input
            type="text"
            value={projectName}
            onChange={(e) => onProjectNameChange(e.target.value)}
            placeholder="project name"
            className="w-full rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm text-gray-200 placeholder-gray-600 focus:border-gray-500 focus:outline-none"
          />
        </div>
        <div className="flex flex-wrap gap-3">
          {Object.entries(result.outputs).map(([key, data]) => {
            const label = OUTPUT_LABELS[key];
            if (!label || !data) return null;
            return (
              <DownloadButton
                key={key}
                data={data}
                filename={filenames[key]}
                label={label}
              />
            );
          })}
        </div>
      </div>
    </div>
  );
}
