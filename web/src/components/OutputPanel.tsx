import type { ProcessResult } from "../worker/workerClient";
import { ImagePreview } from "./ImagePreview";
import { DownloadButton } from "./DownloadButton";

interface Props {
  result: ProcessResult;
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

export function OutputPanel({ result }: Props) {
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
        <div className="flex flex-wrap gap-3">
          {result.outputs.pixels_tiff && (
            <DownloadButton
              data={result.outputs.pixels_tiff}
              filename="pixels.tiff"
              label="Pixels TIFF"
            />
          )}
          {result.outputs.grid_tiff && (
            <DownloadButton
              data={result.outputs.grid_tiff}
              filename="grid.tiff"
              label="Grid TIFF"
            />
          )}
          {result.outputs.experiment_json && (
            <DownloadButton
              data={result.outputs.experiment_json}
              filename="experiment.json"
              label="Experiment JSON"
            />
          )}
          {result.outputs.azimuthal_csv && (
            <DownloadButton
              data={result.outputs.azimuthal_csv}
              filename="azimuthal.csv"
              label="Azimuthal CSV"
            />
          )}
          {result.outputs.radial_csv && (
            <DownloadButton
              data={result.outputs.radial_csv}
              filename="radial.csv"
              label="Radial CSV"
            />
          )}
        </div>
      </div>
    </div>
  );
}
