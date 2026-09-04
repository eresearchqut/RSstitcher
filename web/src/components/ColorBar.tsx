import { useEffect, useRef } from "react";

interface Props {
  /** 256 RGB triplets, as in colormaps.ts. */
  lut: Uint8Array;
  /** Intensity drawn as the bottom of the bar. */
  low: number;
  /** Intensity drawn as the top of the bar; higher cells saturate. */
  high: number;
  format: (value: number) => string;
  /** Percentile window [lower, upper] shown against the end labels. */
  percentiles?: [number, number];
}

const TICKS = [0, 0.25, 0.5, 0.75, 1];

/**
 * Vertical key for the preview's colour map, as tall as the map beside it.
 * Labels mark the window bounds and three points in between so approximate
 * intensities can be read off without hovering; the end labels also carry
 * the window percentiles. When both bounds resolve to the same intensity
 * (common on mostly-empty maps) the rendering is binary, so instead of a
 * gradient with five identical labels the bar shows its two real colours:
 * black for cells at or below the bound, the top of the map above it.
 */
export function ColorBar({ lut, low, high, format, percentiles }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const hasBounds = Number.isFinite(low) && Number.isFinite(high);
  const binary = hasBounds && low === high;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = 1;
    canvas.height = 256;
    const ctx = canvas.getContext("2d")!;
    const image = ctx.createImageData(1, 256);
    for (let y = 0; y < 256; y++) {
      // Binary window: top half is the map's top colour, bottom half black.
      const on = !binary || y < 128;
      const k = binary ? 255 * 3 : (255 - y) * 3;
      image.data[y * 4] = on ? lut[k] : 0;
      image.data[y * 4 + 1] = on ? lut[k + 1] : 0;
      image.data[y * 4 + 2] = on ? lut[k + 2] : 0;
      image.data[y * 4 + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
  }, [lut, binary]);

  return (
    <div className="flex shrink-0 gap-1 text-[10px] leading-none text-gray-400 tabular-nums">
      {/* Absolutely positioned so the 1 x 256 canvas adds no height of its
          own to the row; it stretches to whatever the map beside it is. */}
      <div className="relative w-3">
        <canvas
          ref={canvasRef}
          className="absolute inset-0 h-full w-full rounded-sm border border-gray-700"
        />
      </div>
      <div className="relative w-14">
        {binary
          ? [
              { half: 0.75, label: `> ${format(low)}`, pct: percentiles?.[1] },
              { half: 0.25, label: `≤ ${format(low)}`, pct: percentiles?.[0] },
            ].map(({ half, label, pct }) => (
              <span
                key={half}
                className="absolute left-0 whitespace-nowrap"
                style={{
                  bottom: `${half * 100}%`,
                  transform: "translateY(50%)",
                }}
              >
                <span className="flex items-center gap-1">
                  <span className="h-px w-1 bg-gray-500" />
                  {label}
                </span>
                {pct !== undefined && (
                  <span className="block pl-2 text-gray-500">{pct}%</span>
                )}
              </span>
            ))
          : hasBounds &&
            TICKS.map((t) => (
              <span
                key={t}
                className="absolute left-0 whitespace-nowrap"
                style={
                  t === 1
                    ? { top: 0 }
                    : t === 0
                      ? { bottom: 0 }
                      : { bottom: `${t * 100}%`, transform: "translateY(50%)" }
                }
              >
                {t === 0 && percentiles && (
                  <span className="block pl-2 text-gray-500">
                    {percentiles[0]}%
                  </span>
                )}
                <span className="flex items-center gap-1">
                  <span className="h-px w-1 bg-gray-500" />
                  {t === 1 ? "≥ " : ""}
                  {format(low + t * (high - low))}
                </span>
                {t === 1 && percentiles && (
                  <span className="block pl-2 text-gray-500">
                    {percentiles[1]}%
                  </span>
                )}
              </span>
            ))}
      </div>
    </div>
  );
}
