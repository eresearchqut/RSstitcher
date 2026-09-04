import { useEffect, useRef } from "react";

interface Props {
  /** 256 RGB triplets, as in colormaps.ts. */
  lut: Uint8Array;
  /** Intensity drawn as the bottom of the bar. */
  low: number;
  /** Intensity drawn as the top of the bar; higher cells saturate. */
  high: number;
  format: (value: number) => string;
}

const TICKS = [0, 0.25, 0.5, 0.75, 1];

/**
 * Vertical key for the preview's colour map, as tall as the map beside it.
 * Labels mark the window bounds and three points in between so approximate
 * intensities can be read off without hovering.
 */
export function ColorBar({ lut, low, high, format }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    canvas.width = 1;
    canvas.height = 256;
    const ctx = canvas.getContext("2d")!;
    const image = ctx.createImageData(1, 256);
    for (let y = 0; y < 256; y++) {
      const k = (255 - y) * 3;
      image.data[y * 4] = lut[k];
      image.data[y * 4 + 1] = lut[k + 1];
      image.data[y * 4 + 2] = lut[k + 2];
      image.data[y * 4 + 3] = 255;
    }
    ctx.putImageData(image, 0, 0);
  }, [lut]);

  const hasBounds = Number.isFinite(low) && Number.isFinite(high);

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
        {hasBounds &&
          TICKS.map((t) => (
            <span
              key={t}
              className="absolute left-0 flex items-center gap-1 whitespace-nowrap"
              style={
                t === 1
                  ? { top: 0 }
                  : t === 0
                    ? { bottom: 0 }
                    : { bottom: `${t * 100}%`, transform: "translateY(50%)" }
              }
            >
              <span className="h-px w-1 bg-gray-500" />
              {t === 1 ? "≥ " : ""}
              {format(low + t * (high - low))}
            </span>
          ))}
      </div>
    </div>
  );
}
