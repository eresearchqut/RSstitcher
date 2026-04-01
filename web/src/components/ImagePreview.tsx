import { useEffect, useRef, useState, useCallback, useMemo } from "react";

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

  const [brightness, setBrightness] = useState(50);
  const [showGrid, setShowGrid] = useState(false);
  const [view, setView] = useState<View>({ zoom: 1, panX: 0, panY: 0 });
  const [tooltip, setTooltip] = useState<{
    x: number;
    y: number;
    sz: number;
    sx: number;
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

  const [rows, cols] = arrayShape;
  const outRows = cols;
  const outCols = rows;
  const sxLabel = mode === "gid" ? "Sr" : "Sx";

  // --- Canvas rendering (unchanged logic) ---
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const float32 = new Float32Array(arrayData);
    const grid = new Uint8Array(gridData);

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
    const gamma = Math.pow(2, (50 - brightness) / 12.5);

    canvas.width = outCols;
    canvas.height = outRows;
    const ctx = canvas.getContext("2d")!;
    const imageData = ctx.createImageData(outCols, outRows);
    const pixels = imageData.data;

    for (let i = 0; i < rows; i++) {
      for (let j = 0; j < cols; j++) {
        const srcIdx = i * cols + j;
        const v = float32[srcIdx];
        const normalized = isNaN(v) || !isFinite(v) ? 0 : (v - min) / range;
        const gray = Math.round(Math.pow(normalized, gamma) * 255);
        const dstIdx = ((outRows - 1 - j) * outCols + (outCols - 1 - i)) * 4;

        if (showGrid && grid[srcIdx]) {
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
  }, [
    arrayData,
    arrayShape,
    gridData,
    rows,
    cols,
    brightness,
    showGrid,
    outRows,
    outCols,
  ]);

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
  const mouseToCoords = useCallback(
    (clientX: number, clientY: number) => {
      const vp = viewportRef.current;
      if (!vp) return null;

      const rect = vp.getBoundingClientRect();
      const mx = clientX - rect.left;
      const my = clientY - rect.top;
      const { w, h, ox, oy } = canvasBaseRef.current;
      if (w === 0 || h === 0) return null;

      const cx = (mx - ox - view.panX) / view.zoom;
      const cy = (my - oy - view.panY) / view.zoom;

      const px = (cx / w) * outCols;
      const py = (cy / h) * outRows;
      if (px < 0 || px >= outCols || py < 0 || py >= outRows) return null;

      const sx = sxRange[0] + (px / (outCols - 1)) * (sxRange[1] - sxRange[0]);
      const sz = szRange[1] - (py / (outRows - 1)) * (szRange[1] - szRange[0]);

      return { screenX: mx, screenY: my, sz, sx };
    },
    [view, outCols, outRows, sxRange, szRange],
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
      {/* Viewport (canvas area) */}
      <div
        ref={viewportRef}
        className={`relative overflow-hidden border border-gray-700 bg-black ${isFullscreen ? "min-h-0 flex-1" : ""}`}
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
              left: Math.min(tooltip.x + 14, viewportSize.width - 200),
              top: tooltip.y < 40 ? tooltip.y + 20 : tooltip.y - 32,
            }}
          >
            Sz: {tooltip.sz.toFixed(4)} {"\u00C5\u207B\u00B9"} &ensp; {sxLabel}:{" "}
            {tooltip.sx.toFixed(4)} {"\u00C5\u207B\u00B9"}
          </div>
        )}
      </div>

      {/* Controls */}
      <div
        className={`mt-2 flex items-center gap-6 ${isFullscreen ? "shrink-0 px-4 pt-2 pb-3" : ""}`}
      >
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
            (Reciprocal Space Scale S = 1/d, {"\u0394"}S = 0.1{" "}
            {"\u00C5\u207B\u00B9"})
          </span>
        </label>
      </div>
    </div>
  );
}
