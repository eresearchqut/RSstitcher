import { useEffect, useRef, useState } from "react";

interface Props {
  arrayData: ArrayBuffer;
  arrayShape: [number, number];
  gridData: ArrayBuffer;
}

export function ImagePreview({ arrayData, arrayShape, gridData }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [brightness, setBrightness] = useState(50);
  const [showGrid, setShowGrid] = useState(false);
  const [rows, cols] = arrayShape;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const float32 = new Float32Array(arrayData);
    const grid = new Uint8Array(gridData);

    // Apply the same rotation as write_pixels_tiff: fliplr(rot90(arr, 1))
    const outRows = cols;
    const outCols = rows;

    // Find min/max ignoring NaN
    let min = Infinity;
    let max = -Infinity;
    for (let i = 0; i < float32.length; i++) {
      const v = float32[i];
      if (!isNaN(v) && isFinite(v)) {
        if (v < min) min = v;
        if (v > max) max = v;
      }
    }
    const range = max - min || 1;

    // Map slider 0-100 to gamma 4.0-0.25 (left=dark, right=bright)
    // 50 = gamma 1.0 (linear)
    const gamma = Math.pow(2, (50 - brightness) / 12.5);

    canvas.width = outCols;
    canvas.height = outRows;
    const ctx = canvas.getContext("2d")!;
    const imageData = ctx.createImageData(outCols, outRows);
    const pixels = imageData.data;

    // Transpose + vertical flip to match TIFF orientation
    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const srcIdx = i * cols + j;
        const v = float32[srcIdx];
        const normalized = isNaN(v) || !isFinite(v) ? 0 : (v - min) / range;
        const gray = Math.round(Math.pow(normalized, gamma) * 255);

        const dstIdx = ((outRows - 1 - j) * outCols + (outCols - 1 - i)) * 4;

        if (showGrid && grid[srcIdx]) {
          // Grid line: cyan overlay
          pixels[dstIdx] = 0;
          pixels[dstIdx + 1] = 200;
          pixels[dstIdx + 2] = 255;
        } else {
          pixels[dstIdx] = gray;
          pixels[dstIdx + 1] = gray;
          pixels[dstIdx + 2] = gray;
        }
        pixels[dstIdx + 3] = 255;
      }
    }

    ctx.putImageData(imageData, 0, 0);
  }, [arrayData, arrayShape, gridData, rows, cols, brightness, showGrid]);

  return (
    <div>
      <canvas
        ref={canvasRef}
        className="h-auto w-full border border-gray-700 bg-black"
        style={{ imageRendering: "pixelated" }}
      />
      <div className="mt-2 flex items-center gap-6">
        <div className="flex items-center gap-3">
          <label className="shrink-0 text-xs text-gray-500">Brightness</label>
          <input
            type="range"
            min={0}
            max={100}
            value={brightness}
            onChange={(e) => setBrightness(Number(e.target.value))}
            className="w-48 accent-blue-500"
          />
        </div>
        <label className="flex items-center gap-1.5 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={showGrid}
            onChange={(e) => setShowGrid(e.target.checked)}
            className="rounded"
          />
          Show grid overlay{" "}
          <span className="text-xs text-gray-500">
            (Reciprocal Space Scale S = 1/d, ΔS = 0.1 Å⁻¹)
          </span>
        </label>
      </div>
    </div>
  );
}
