import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { COLORMAPS } from "../colormaps";
import { ColorBar } from "./ColorBar";
import { RangeSlider } from "./RangeSlider";

interface Props {
  arrayData: ArrayBuffer;
  arrayShape: [number, number];
  gridData: ArrayBuffer;
  mode: string;
  sxRange: [number, number];
  szRange: [number, number];
}

interface View {
  zoom: number;
  panX: number;
  panY: number;
}

function formatIntensity(value: number, digits = 6): string {
  if (Number.isNaN(value)) return "no data";
  if (!Number.isFinite(value)) return value > 0 ? "inf" : "-inf";
  return String(Number(value.toPrecision(digits)));
}

const DEFAULT_PERCENTILES: [number, number] = [5, 95];
/** Percentage points each end moves per Narrow or Widen click. */
const WINDOW_STEP = 2.5;

export function ImagePreview({
  arrayData,
  arrayShape,
  gridData,
  mode,
  sxRange,
  szRange,
}: Props) {
  const wrapperRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  // Lower and upper percentile of the finite cells, as ImageJ's auto
  // contrast sets its bounds: cells at or below the lower bound draw black,
  // cells at or above the upper bound draw as the top of the colour map.
  const [percentiles, setPercentiles] =
    useState<[number, number]>(DEFAULT_PERCENTILES);
  const [colormapId, setColormapId] = useState(COLORMAPS[0].id);
  const [showGrid, setShowGrid] = useState(false);
  const [view, setView] = useState<View>({ zoom: 1, panX: 0, panY: 0 });
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    sz: number;
    sx: number;
    intensity: number;
  } | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [viewportSize, setViewportSize] = useState({ width: 0, height: 0 });

  const dragInfo = useRef<{
    startX: number;
    startY: number;
    startPanX: number;
    startPanY: number;
  } | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  // The array is indexed [sx, sz]; the preview shows np.rot90(array, 1)
  // exactly as the TIFF writers do: output[r, c] = array[c, cols - 1 - r],
  // so Sx increases left to right and Sz increases bottom to top.
  const [rows, cols] = arrayShape;
  const outRows = cols;
  const outCols = rows;
  const sxLabel = mode === "gid" ? "Sr" : "Sx";

  const float32 = useMemo(() => new Float32Array(arrayData), [arrayData]);
  const grid = useMemo(() => new Uint8Array(gridData), [gridData]);

  // Finite cell values in ascending order, computed once per result so
  // dragging the window handles only re-maps the canvas.
  const sortedFinite = useMemo(() => {
    const finite = new Float32Array(float32.length);
    let n = 0;
    for (let i = 0; i < float32.length; i++) {
      const v = float32[i];
      if (Number.isFinite(v)) finite[n++] = v;
    }
    return finite.subarray(0, n).sort();
  }, [float32]);

  const bounds = useMemo((): [number, number] => {
    const n = sortedFinite.length;
    if (n === 0) return [NaN, NaN];
    const at = (p: number) => sortedFinite[Math.round((p / 100) * (n - 1))];
    return [at(percentiles[0]), at(percentiles[1])];
  }, [sortedFinite, percentiles]);

  const colormap = COLORMAPS.find((c) => c.id === colormapId) ?? COLORMAPS[0];

  // Move both ends of the window inward (positive step) or outward,
  // clamped to the percentile range and never crossing.
  const nudgeWindow = (step: number) =>
    setPercentiles(([lo, hi]) => {
      const nextLo = Math.max(0, lo + step);
      const nextHi = Math.min(100, hi - step);
      if (nextLo <= nextHi) return [nextLo, nextHi];
      const mid = Math.round(((lo + hi) / 2) * 2) / 2;
      return [mid, mid];
    });
  const isDefaultWindow =
    percentiles[0] === DEFAULT_PERCENTILES[0] &&
    percentiles[1] === DEFAULT_PERCENTILES[1];

  // --- Canvas rendering ---
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const [low, high] = bounds;
    const span = high - low;
    const lut = colormap.lut;

    canvas.width = outCols;
    canvas.height = outRows;
    const ctx = canvas.getContext("2d")!;
    const imageData = ctx.createImageData(outCols, outRows);
    const pixels = imageData.data;

    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const srcIdx = i * cols + j;
        const v = float32[srcIdx];
        const dstIdx = ((cols - 1 - j) * outCols + i) * 4;

        if (showGrid && grid[srcIdx]) {
          pixels[dstIdx] = 0;
          pixels[dstIdx + 1] = 200;
          pixels[dstIdx + 2] = 255;
        } else if (Number.isFinite(v) && v > low) {
          // Empty cells and cells at or below the lower bound stay black.
          const t = span > 0 ? Math.min((v - low) / span, 1) : 1;
          const k = Math.round(t * 255) * 3;
          pixels[dstIdx] = lut[k];
          pixels[dstIdx + 1] = lut[k + 1];
          pixels[dstIdx + 2] = lut[k + 2];
        }
        pixels[dstIdx + 3] = 255;
      }
    }

    ctx.putImageData(imageData, 0, 0);
  }, [float32, grid, rows, cols, bounds, colormap, showGrid, outRows, outCols]);

  // --- Track viewport dimensions ---
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const { width, height } = entries[0].contentRect;
      setViewportSize({ width, height });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // --- Canvas base size (fit within viewport preserving aspect ratio) ---
  const canvasBase = useMemo(() => {
    const { width: vw, height: vh } = viewportSize;
    if (vw === 0 || vh === 0) return { w: 0, h: 0, ox: 0, oy: 0 };

    const aspect = outCols / outRows;
    const vpAspect = vw / vh;

    let w: number, h: number;
    if (vpAspect > aspect) {
      h = vh;
      w = h * aspect;
    } else {
      w = vw;
      h = w / aspect;
    }
    return { w, h, ox: (vw - w) / 2, oy: (vh - h) / 2 };
  }, [viewportSize, outCols, outRows]);

  // Keep a ref so wheel/mouse handlers always see the latest
  const canvasBaseRef = useRef(canvasBase);
  useEffect(() => {
    canvasBaseRef.current = canvasBase;
  }, [canvasBase]);

  // --- Wheel zoom (centered on cursor) ---
  const handleWheel = useCallback((e: WheelEvent) => {
    e.preventDefault();
    const vp = viewportRef.current;
    if (!vp) return;

    const rect = vp.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15;
    const { ox, oy } = canvasBaseRef.current;

    setView((prev) => {
      const newZoom = Math.max(1, Math.min(100, prev.zoom * factor));
      const rx = mx - ox;
      const ry = my - oy;
      const cx = (rx - prev.panX) / prev.zoom;
      const cy = (ry - prev.panY) / prev.zoom;
      return {
        zoom: newZoom,
        panX: rx - cx * newZoom,
        panY: ry - cy * newZoom,
      };
    });
  }, []);

  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => el.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  // --- Mouse-to-reciprocal-space coordinate mapping ---
  // The canvas rect already carries the zoom/pan transform and sits inside
  // the viewport's border, so measure against the canvas itself.
  const mouseToCoords = useCallback(
    (clientX: number, clientY: number) => {
      const vp = viewportRef.current;
      const canvas = canvasRef.current;
      if (!vp || !canvas) return null;

      const vpRect = vp.getBoundingClientRect();
      const rect = canvas.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return null;

      const pxf = ((clientX - rect.left) / rect.width) * outCols;
      const pyf = ((clientY - rect.top) / rect.height) * outRows;
      if (pxf < 0 || pxf >= outCols || pyf < 0 || pyf >= outRows) return null;

      const px = Math.min(Math.floor(pxf), outCols - 1);
      const py = Math.min(Math.floor(pyf), outRows - 1);

      const sx = sxRange[0] + (px / (outCols - 1)) * (sxRange[1] - sxRange[0]);
      const sz = szRange[1] - (py / (outRows - 1)) * (szRange[1] - szRange[0]);
      const intensity = float32[px * cols + (cols - 1 - py)];

      return {
        screenX: clientX - vpRect.left,
        screenY: clientY - vpRect.top,
        sz,
        sx,
        intensity,
      };
    },
    [outCols, outRows, cols, sxRange, szRange, float32],
  );

  // --- Drag to pan ---
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    dragInfo.current = {
      startX: e.clientX,
      startY: e.clientY,
      startPanX: view.panX,
      startPanY: view.panY,
    };
    setIsDragging(true);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const drag = dragInfo.current;
    if (drag) {
      const dx = e.clientX - drag.startX;
      const dy = e.clientY - drag.startY;
      const newPanX = drag.startPanX + dx;
      const newPanY = drag.startPanY + dy;
      setView((prev) => ({
        ...prev,
        panX: newPanX,
        panY: newPanY,
      }));
      setTooltip(null);
      return;
    }

    const coords = mouseToCoords(e.clientX, e.clientY);
    if (coords) {
      setTooltip({
        x: coords.screenX,
        y: coords.screenY,
        sz: coords.sz,
        sx: coords.sx,
        intensity: coords.intensity,
      });
    } else {
      setTooltip(null);
    }
  };

  const handleMouseUp = () => {
    dragInfo.current = null;
    setIsDragging(false);
  };

  const handleMouseLeave = () => {
    dragInfo.current = null;
    setIsDragging(false);
    setTooltip(null);
  };

  // Double-click resets view
  const handleDoubleClick = () => setView({ zoom: 1, panX: 0, panY: 0 });

  // --- Fullscreen ---
  const toggleFullscreen = (e: React.MouseEvent) => {
    e.stopPropagation();
    const el = wrapperRef.current;
    if (!el) return;
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      el.requestFullscreen();
    }
  };

  useEffect(() => {
    const handler = () => {
      setIsFullscreen(!!document.fullscreenElement);
      setView({ zoom: 1, panX: 0, panY: 0 });
    };
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  return (
    <div
      ref={wrapperRef}
      className={isFullscreen ? "flex h-full flex-col bg-black" : ""}
    >
      {/* Viewport (canvas area) with the colour key beside it */}
      <div className={`flex gap-2 ${isFullscreen ? "min-h-0 flex-1 p-2" : ""}`}>
        <div
          ref={viewportRef}
          className="relative min-w-0 flex-1 overflow-hidden border border-gray-700 bg-black"
          style={isFullscreen ? {} : { aspectRatio: `${outCols} / ${outRows}` }}
          onMouseDown={handleMouseDown}
          onMouseMove={handleMouseMove}
          onMouseUp={handleMouseUp}
          onMouseLeave={handleMouseLeave}
          onDoubleClick={handleDoubleClick}
        >
          <canvas
            ref={canvasRef}
            style={{
              position: "absolute",
              left: canvasBase.ox,
              top: canvasBase.oy,
              width: canvasBase.w,
              height: canvasBase.h,
              imageRendering: "pixelated" as const,
              transformOrigin: "0 0",
              transform: `translate(${view.panX}px, ${view.panY}px) scale(${view.zoom})`,
              cursor: isDragging ? "grabbing" : "crosshair",
            }}
          />

          {/* Fullscreen button */}
          <button
            onClick={toggleFullscreen}
            className="absolute top-2 right-2 rounded bg-gray-800/70 p-1.5 text-gray-400 hover:bg-gray-700 hover:text-white"
            title={isFullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
          >
            {isFullscreen ? (
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <polyline points="6,1 6,6 1,6" />
                <polyline points="10,15 10,10 15,10" />
                <polyline points="15,6 10,6 10,1" />
                <polyline points="1,10 6,10 6,15" />
              </svg>
            ) : (
              <svg
                width="16"
                height="16"
                viewBox="0 0 16 16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.5"
              >
                <polyline points="1,6 1,1 6,1" />
                <polyline points="15,10 15,15 10,15" />
                <polyline points="10,1 15,1 15,6" />
                <polyline points="6,15 1,15 1,10" />
              </svg>
            )}
          </button>

          {/* Zoom indicator + reset */}
          {view.zoom > 1 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                setView({ zoom: 1, panX: 0, panY: 0 });
              }}
              className="absolute bottom-2 left-2 rounded bg-black/60 px-2 py-0.5 text-xs text-gray-400 hover:text-white"
              title="Reset zoom (double-click)"
            >
              {view.zoom.toFixed(1)}x
            </button>
          )}

          {/* Tooltip */}
          {tooltip && (
            <div
              className="pointer-events-none absolute z-10 rounded border border-gray-600 bg-gray-900/90 px-2 py-1 text-xs whitespace-nowrap text-gray-200"
              style={{
                left: Math.min(tooltip.x + 14, viewportSize.width - 220),
                top: tooltip.y < 56 ? tooltip.y + 20 : tooltip.y - 48,
              }}
            >
              <div>
                Sz: {tooltip.sz.toFixed(4)} {"\u00C5\u207B\u00B9"} &ensp;{" "}
                {sxLabel}: {tooltip.sx.toFixed(4)} {"\u00C5\u207B\u00B9"}
              </div>
              <div>Intensity: {formatIntensity(tooltip.intensity)}</div>
            </div>
          )}
        </div>
        <ColorBar
          lut={colormap.lut}
          low={bounds[0]}
          high={bounds[1]}
          format={(v) => formatIntensity(v, 3)}
        />
      </div>

      {/* Controls */}
      <div
        className={`mt-2 flex flex-wrap items-center gap-x-6 gap-y-2 ${isFullscreen ? "shrink-0 px-4 pt-2 pb-3" : ""}`}
      >
        <div className="flex items-center gap-3">
          <span className="shrink-0 text-xs text-gray-500">
            Intensity window
          </span>
          <RangeSlider
            min={0}
            max={100}
            step={0.5}
            value={percentiles}
            onChange={setPercentiles}
            labels={["Lower percentile", "Upper percentile"]}
            className="w-48"
          />
          <span className="text-xs text-gray-400 tabular-nums">
            {percentiles[0]}% to {percentiles[1]}%
          </span>
          <span className="text-xs text-gray-500 tabular-nums">
            ({formatIntensity(bounds[0], 3)} to {formatIntensity(bounds[1], 3)})
          </span>
          <span className="flex gap-1">
            <button
              type="button"
              onClick={() => nudgeWindow(WINDOW_STEP)}
              disabled={percentiles[0] === percentiles[1]}
              title={`Move both ends inward by ${WINDOW_STEP} points`}
              className="rounded border border-gray-700 px-1.5 py-0.5 text-xs text-gray-400 hover:text-white disabled:text-gray-600 disabled:hover:text-gray-600"
            >
              Narrow
            </button>
            <button
              type="button"
              onClick={() => nudgeWindow(-WINDOW_STEP)}
              disabled={percentiles[0] === 0 && percentiles[1] === 100}
              title={`Move both ends outward by ${WINDOW_STEP} points`}
              className="rounded border border-gray-700 px-1.5 py-0.5 text-xs text-gray-400 hover:text-white disabled:text-gray-600 disabled:hover:text-gray-600"
            >
              Widen
            </button>
            <button
              type="button"
              onClick={() => setPercentiles(DEFAULT_PERCENTILES)}
              disabled={isDefaultWindow}
              title={`Back to ${DEFAULT_PERCENTILES[0]}% to ${DEFAULT_PERCENTILES[1]}%`}
              className="rounded border border-gray-700 px-1.5 py-0.5 text-xs text-gray-400 hover:text-white disabled:text-gray-600 disabled:hover:text-gray-600"
            >
              Reset
            </button>
          </span>
        </div>
        <label className="flex items-center gap-2 text-xs text-gray-500">
          Colour map
          <select
            value={colormap.id}
            onChange={(e) => setColormapId(e.target.value)}
            className="rounded border border-gray-700 bg-gray-800 px-2 py-0.5 text-xs text-gray-300"
          >
            {COLORMAPS.map((c) => (
              <option key={c.id} value={c.id}>
                {c.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5 text-xs text-gray-500">
          <input
            type="checkbox"
            checked={showGrid}
            onChange={(e) => setShowGrid(e.target.checked)}
            className="rounded"
          />
          Show grid overlay{" "}
          <span className="text-xs text-gray-500">
            (Reciprocal Space Scale S = 1/d, {"\u0394"}S = 0.1{" "}
            {"\u00C5\u207B\u00B9"})
          </span>
        </label>
      </div>
    </div>
  );
}
