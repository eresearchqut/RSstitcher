import { useEffect, useRef, useCallback, useState, useMemo } from "react";
import type { View } from "vega";

interface Props {
  /** Raw CSV file as ArrayBuffer */
  data: ArrayBuffer;
  /** "azimuthal" or "radial" — determines axis labels and parsing */
  kind: "azimuthal" | "radial";
  /** Filename (without extension) for PNG export */
  exportName?: string;
}

const POINT_STYLE = {
  size: 6,
  filled: true as const,
  fill: "white",
  strokeWidth: 0,
};

/** Parse CSV text into an array of row objects. */
function parseCsv(text: string): {
  headers: string[];
  rows: Record<string, number>[];
} {
  const lines = text.trim().split("\n");
  if (lines.length < 2) return { headers: [], rows: [] };

  const headers = lines[0].split(",").map((h) => h.trim());
  const rows: Record<string, number>[] = [];
  for (let i = 1; i < lines.length; i++) {
    const values = lines[i].split(",");
    const row: Record<string, number> = {};
    for (let j = 0; j < headers.length; j++) {
      row[headers[j]] = parseFloat(values[j]);
    }
    rows.push(row);
  }
  return { headers, rows };
}

/**
 * Reshape wide-format CSV into long-format for Vega-Lite:
 *   { x, series, y } for each (row, value-column) pair.
 */
function toLong(
  headers: string[],
  rows: Record<string, number>[],
  xCol: string,
): { x: number; series: string; y: number }[] {
  const valueCols = headers.filter((h) => h !== xCol);
  const long: { x: number; series: string; y: number }[] = [];
  for (const row of rows) {
    for (const col of valueCols) {
      const y = row[col];
      if (!isNaN(y)) {
        long.push({ x: row[xCol], series: col, y });
      }
    }
  }
  return long;
}

export function CsvChart({ data, kind, exportName }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewRef = useRef<View | null>(null);
  const [showPoints, setShowPoints] = useState(false);

  const handleReset = useCallback(() => {
    const view = viewRef.current;
    if (!view) return;
    view.signal("grid_x", null);
    view.signal("grid_y", null);
    view.run();
  }, []);

  const handleSavePng = useCallback(() => {
    const view = viewRef.current;
    if (!view) return;
    view.toImageURL("png", 2).then((url) => {
      const a = document.createElement("a");
      a.href = url;
      a.download = `${exportName || kind}.png`;
      a.click();
    });
  }, [exportName, kind]);

  const pointSetting = useMemo(
    () => (showPoints ? POINT_STYLE : false),
    [showPoints],
  );

  useEffect(() => {
    if (!containerRef.current) return;

    const text = new TextDecoder().decode(data);
    const { headers, rows } = parseCsv(text);
    if (headers.length < 2 || rows.length === 0) return;

    const xCol = headers[0];
    const values = toLong(headers, rows, xCol);

    const xLabel =
      kind === "azimuthal" ? "Radius (S\u207B\u00B9)" : "Angle (\u00B0)";
    const yLabel = "Intensity";

    let cancelled = false;

    import("vega-embed").then(({ default: embed }) => {
      if (cancelled || !containerRef.current) return;

      embed(
        containerRef.current,
        {
          $schema: "https://vega.github.io/schema/vega-lite/v5.json",
          width: "container",
          height: 260,
          background: "transparent",
          data: { values },
          params: [
            {
              name: "grid",
              select: { type: "interval" },
              bind: "scales",
            },
            {
              name: "hover",
              select: {
                type: "point",
                fields: ["series"],
                on: "pointerover",
                clear: "pointerout",
              },
            },
            {
              name: "seriesFilter",
              select: { type: "point", fields: ["series"] },
              bind: "legend",
            },
          ],
          mark: {
            type: "line",
            strokeWidth: 1.5,
            point: pointSetting,
          },
          encoding: {
            x: {
              field: "x",
              type: "quantitative",
              title: xLabel,
              axis: {
                labelColor: "#9ca3af",
                titleColor: "#9ca3af",
                gridColor: "#374151",
              },
            },
            y: {
              field: "y",
              type: "quantitative",
              title: yLabel,
              axis: {
                labelColor: "#9ca3af",
                titleColor: "#9ca3af",
                gridColor: "#374151",
              },
            },
            color: {
              field: "series",
              type: "nominal",
              title: kind === "azimuthal" ? "Sector" : "Radial bin",
              legend: { labelColor: "#9ca3af", titleColor: "#9ca3af" },
            },
            opacity: {
              condition: { param: "seriesFilter", value: 1 },
              value: 0.1,
            },
            strokeWidth: {
              condition: { param: "hover", empty: false, value: 3 },
              value: 1.5,
            },
            tooltip: [
              {
                field: "x",
                type: "quantitative",
                title: xLabel,
                format: ".4f",
              },
              {
                field: "y",
                type: "quantitative",
                title: yLabel,
                format: ".2f",
              },
              { field: "series", type: "nominal", title: "Series" },
            ],
          },
          config: {
            view: { stroke: "transparent" },
            axis: { domainColor: "#4b5563" },
          },
        },
        { actions: false, renderer: "canvas" },
      ).then((res) => {
        if (cancelled) {
          res.finalize();
        } else {
          viewRef.current = res.view;
        }
      });
    });

    return () => {
      cancelled = true;
      viewRef.current = null;
    };
  }, [data, kind, pointSetting]);

  return (
    <div>
      <div ref={containerRef} className="w-full" />
      <div className="mt-1 flex items-center justify-between">
        <p className="text-xs text-gray-600">
          Scroll to zoom. Drag to pan. Click legend to toggle series.
        </p>
        <div className="flex gap-3">
          <label className="flex cursor-pointer items-center gap-1 text-xs text-gray-500 hover:text-gray-300">
            <input
              type="checkbox"
              checked={showPoints}
              onChange={(e) => setShowPoints(e.target.checked)}
              className="rounded"
            />
            Points
          </label>
          <button
            onClick={handleSavePng}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Save PNG
          </button>
          <button
            onClick={handleReset}
            className="text-xs text-gray-500 hover:text-gray-300"
          >
            Reset zoom
          </button>
        </div>
      </div>
    </div>
  );
}
