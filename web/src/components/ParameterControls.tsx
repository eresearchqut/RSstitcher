import type { ProcessParams } from "../worker/types";

interface Props {
  params: ProcessParams;
  onChange: (params: ProcessParams) => void;
  disabled: boolean;
}

export function ParameterControls({ params, onChange, disabled }: Props) {
  const update = (partial: Partial<ProcessParams>) =>
    onChange({ ...params, ...partial });

  return (
    <div className="grid grid-cols-2 gap-4">
      <label className="block">
        <span className="text-sm text-gray-400">Diffraction geometry</span>
        <select
          value={params.mode}
          onChange={(e) =>
            update({ mode: e.target.value as ProcessParams["mode"] })
          }
          disabled={disabled}
          className="mt-1 block w-full rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm"
        >
          <option value="auto">Auto-detect</option>
          <option value="symmetric">Symmetric</option>
          <option value="gid">GID</option>
        </select>
      </label>

      <label className="block">
        <span className="text-sm text-gray-400">Intensity</span>
        <select
          value={params.scale}
          onChange={(e) =>
            update({ scale: e.target.value as ProcessParams["scale"] })
          }
          disabled={disabled}
          className="mt-1 block w-full rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm"
        >
          <option value="linear">Linear</option>
          <option value="log">Log</option>
          <option value="sqrt">Sqrt</option>
        </select>
      </label>

      <label className="block">
        <span className="text-sm text-gray-400">Phi tolerance (deg)</span>
        <input
          type="number"
          value={params.phiTolerance}
          onChange={(e) =>
            update({ phiTolerance: parseFloat(e.target.value) || 0 })
          }
          step={0.5}
          min={0}
          disabled={disabled}
          className="mt-1 block w-full rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm"
        />
      </label>

      <label className="block">
        <span className="text-sm text-gray-400">Frame edge blur fraction</span>
        <input
          type="number"
          value={params.blurFraction}
          onChange={(e) =>
            update({ blurFraction: parseFloat(e.target.value) || 0 })
          }
          step={0.05}
          min={0}
          max={1}
          disabled={disabled}
          className="mt-1 block w-full rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm"
        />
      </label>

      <label className="block">
        <span className="text-sm text-gray-400">Zenithal bins</span>
        <span className="block text-xs text-gray-500">
          If requires integration to 1D
        </span>
        <input
          type="number"
          value={params.azimuthalBins ?? ""}
          onChange={(e) =>
            update({
              azimuthalBins: e.target.value ? parseInt(e.target.value) : null,
            })
          }
          placeholder="None"
          min={1}
          disabled={disabled}
          className="mt-1 block w-full rounded border border-gray-700 bg-gray-800 px-3 py-1.5 text-sm"
        />
      </label>

      <div className="block">
        <span className="text-sm text-gray-400">Reciprocal space ticks</span>
        <span className="block text-xs text-gray-500">
          <i>S</i> = 1/<i>d</i> (Δ<i>S</i> = 0.1 Å⁻¹)
        </span>
        <div className="mt-1 flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              checked={params.circles !== null}
              onChange={(e) =>
                update({ circles: e.target.checked ? [-1] : null })
              }
              disabled={disabled}
              className="rounded"
            />
            Export S scale
          </label>
        </div>
      </div>

      <div className="col-span-2">
        <div className="flex items-center justify-between">
          <div>
            <span className="text-sm text-gray-400">Radial bins</span>
            <span className="block text-xs text-gray-500">
              To export Debye ring profile
            </span>
          </div>
          <button
            onClick={() => {
              const current = params.radialBins ?? [];
              update({ radialBins: [...current, [0.1, 1.0]] });
            }}
            disabled={disabled}
            className="text-xs text-blue-400 hover:text-blue-300"
          >
            + Add bin
          </button>
        </div>
        {params.radialBins && params.radialBins.length > 0 && (
          <div className="mt-2 space-y-2">
            {params.radialBins.map((bin, i) => (
              <div key={i} className="flex items-center gap-2">
                <input
                  type="number"
                  value={bin[0]}
                  onChange={(e) => {
                    const bins = [...params.radialBins!];
                    bins[i] = [parseFloat(e.target.value) || 0, bins[i][1]];
                    update({ radialBins: bins });
                  }}
                  step={0.1}
                  placeholder="min"
                  disabled={disabled}
                  className="w-20 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm"
                />
                <span className="text-gray-500">-</span>
                <input
                  type="number"
                  value={bin[1]}
                  onChange={(e) => {
                    const bins = [...params.radialBins!];
                    bins[i] = [bins[i][0], parseFloat(e.target.value) || 0];
                    update({ radialBins: bins });
                  }}
                  step={0.1}
                  placeholder="max"
                  disabled={disabled}
                  className="w-20 rounded border border-gray-700 bg-gray-800 px-2 py-1 text-sm"
                />
                <button
                  onClick={() => {
                    const bins = params.radialBins!.filter((_, j) => j !== i);
                    update({ radialBins: bins.length > 0 ? bins : null });
                  }}
                  disabled={disabled}
                  className="text-sm text-red-400 hover:text-red-300"
                >
                  Remove
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
