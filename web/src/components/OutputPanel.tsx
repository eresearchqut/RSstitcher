import { useMemo } from "react";
import type { ProcessResult } from "../worker/workerClient";
import { OUTPUT_SUFFIXES, expandTemplate } from "../outputUtils";
import { ImagePreview } from "./ImagePreview";
import { DownloadButton } from "./DownloadButton";
import { CsvChart } from "./CsvChart";

interface Props {
  result: ProcessResult;
  projectName: string;
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

export function OutputPanel({ result, projectName }: Props) {
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
      {/* Preview + image downloads */}
      <div>
        <ImagePreview
          arrayData={result.arrayData}
          arrayShape={result.arrayShape}
          gridData={result.gridData}
        />
        <div className="mt-3 flex flex-wrap gap-3">
          {result.outputs.pixels_tiff && (
            <DownloadButton
              data={result.outputs.pixels_tiff}
              filename={filenames.pixels_tiff}
              label="WRRSM TIFF"
            />
          )}
          {result.outputs.grid_tiff && (
            <DownloadButton
              data={result.outputs.grid_tiff}
              filename={filenames.grid_tiff}
              label="S Overlay"
            />
          )}
        </div>
      </div>

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
        {result.outputs.experiment_json && (
          <div className="mt-3">
            <DownloadButton
              data={result.outputs.experiment_json}
              filename={filenames.experiment_json}
              label="Experiment JSON"
            />
          </div>
        )}
      </div>

      {/* Charts */}
      {result.outputs.azimuthal_csv && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-gray-400">
            1D diffraction patterns
          </h3>
          <CsvChart
            data={result.outputs.azimuthal_csv}
            kind="azimuthal"
            exportName={filenames.azimuthal_csv.replace(/\.csv$/, "")}
          />
          <div className="mt-3">
            <DownloadButton
              data={result.outputs.azimuthal_csv}
              filename={filenames.azimuthal_csv}
              label="1D Diffraction Patterns CSV"
            />
          </div>
        </div>
      )}
      {result.outputs.radial_csv && (
        <div>
          <h3 className="mb-2 text-sm font-medium text-gray-400">
            Debye ring profiles
          </h3>
          <CsvChart
            data={result.outputs.radial_csv}
            kind="radial"
            exportName={filenames.radial_csv.replace(/\.csv$/, "")}
          />
          <div className="mt-3">
            <DownloadButton
              data={result.outputs.radial_csv}
              filename={filenames.radial_csv}
              label="Debye ring profile CSV"
            />
          </div>
        </div>
      )}
    </div>
  );
}
