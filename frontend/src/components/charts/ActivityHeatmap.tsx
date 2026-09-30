"use client";

import { useCallback, useMemo } from "react";

import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, LOCKED_BAR_CONFIG, type ChartTheme } from "./theme";

export interface ActivityRow {
  label: string;
  values: number[];
}

/** Simple mix toward surface for mid-ramp stops. */
function mixHex(color: string, toward: string, towardWeight: number): string {
  const parse = (value: string) => {
    const hex = value.trim().replace("#", "");
    if (hex.length !== 6) return null;
    return [
      Number.parseInt(hex.slice(0, 2), 16),
      Number.parseInt(hex.slice(2, 4), 16),
      Number.parseInt(hex.slice(4, 6), 16),
    ] as const;
  };
  const a = parse(color);
  const b = parse(toward);
  if (!a || !b) return color;
  const mix = (i: number) =>
    Math.round(a[i] * (1 - towardWeight) + b[i] * towardWeight)
      .toString(16)
      .padStart(2, "0");
  return `#${mix(0)}${mix(1)}${mix(2)}`;
}

/**
 * Field × year activity heatmap.
 *
 * Rows are sorted by total volume (highest at top). Colour ramp uses sequential
 * tokens (safer for colour-blind readers than rainbow scales). Hover shows
 * field, year, and count.
 */
export function ActivityHeatmap({
  years,
  rows,
}: {
  years: number[];
  rows: ActivityRow[];
}) {
  const ordered = useMemo(
    () =>
      [...rows].sort(
        (a, b) =>
          b.values.reduce((sum, n) => sum + n, 0) -
          a.values.reduce((sum, n) => sum + n, 0),
      ),
    [rows],
  );

  const build = useCallback(
    (theme: ChartTheme) => ({
      data: [
        {
          type: "heatmap",
          x: years.map(String),
          y: ordered.map((row) => row.label),
          z: ordered.map((row) => row.values),
          colorscale: [
            [0, theme.surface],
            [0.4, mixHex(theme.sequential, theme.surface, 0.55)],
            [0.75, mixHex(theme.sequential, theme.surface, 0.2)],
            [1, theme.sequential],
          ],
          zmin: 0,
          xgap: 4,
          ygap: 4,
          hoverongaps: false,
          texttemplate: "%{z}",
          textfont: { size: 12, color: theme.ink },
          hovertemplate:
            "<b>%{y}</b><br>Year %{x}<br>%{z:,} AI publications<extra></extra>",
          colorbar: {
            thickness: 10,
            len: 0.75,
            tickfont: { size: 12, color: theme.muted },
            title: { text: "Records", font: { size: 12, color: theme.muted } },
          },
        },
      ],
      layout: {
        ...baseLayout(theme),
        margin: { l: 8, r: 10, t: 8, b: 32 },
        xaxis: {
          type: "category",
          side: "bottom",
          tickfont: { size: 12 },
          automargin: true,
          title: { text: "Year", font: { size: 12, color: theme.muted } },
          fixedrange: true,
        },
        yaxis: {
          autorange: "reversed",
          automargin: true,
          tickfont: { size: 12 },
          title: { text: "Field", font: { size: 12, color: theme.muted } },
          fixedrange: true,
        },
        dragmode: false,
      },
    }),
    [years, ordered],
  );

  return (
    <div>
      <PlotlyChart
        build={build}
        height={Math.max(260, ordered.length * 40 + 70)}
        ariaLabel="AI publications by research field and year; darker cells indicate more publications"
        config={LOCKED_BAR_CONFIG}
      />
      <p className="mt-2 text-body-sm text-muted">
        Darker green = more publications. Colour uses the sequential brand ramp
        (safer for colour-blind readers than rainbow scales). Rows sorted by
        total count. Hover a cell for field, year, and exact count.
      </p>
    </div>
  );
}
