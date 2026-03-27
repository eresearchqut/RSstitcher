import { useEffect, useRef } from "react";

interface Props {
  /** Raw CSV file as ArrayBuffer */
  data: ArrayBuffer;
  /** "azimuthal" or "radial" — determines axis labels and parsing */
  kind: "azimuthal" | "radial";
}

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

export function CsvChart({ data, kind }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

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
          mark: { type: "line", strokeWidth: 1.5 },
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
          },
          config: {
            view: { stroke: "transparent" },
            axis: { domainColor: "#4b5563" },
          },
        },
        { actions: false, renderer: "svg" },
      ).then((res) => {
        if (cancelled) res.finalize();
      });
    });

    return () => {
      cancelled = true;
    };
  }, [data, kind]);

  return <div ref={containerRef} className="w-full" />;
}
