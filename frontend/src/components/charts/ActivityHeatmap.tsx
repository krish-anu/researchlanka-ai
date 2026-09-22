"use client";

import { useCallback } from "react";
import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, type ChartTheme } from "./theme";

export interface ActivityRow { label: string; values: number[] }
export function ActivityHeatmap({ years, rows }: { years: number[]; rows: ActivityRow[] }) {
  const build = useCallback((theme: ChartTheme) => ({
    data: [{ type: "heatmap", x: years.map(String), y: rows.map(row => row.label), z: rows.map(row => row.values), colorscale: [[0, theme.surface], [1, theme.sequential]], zmin: 0, xgap: 4, ygap: 4, hoverongaps: false, texttemplate: "%{z}", textfont: { size: 10 }, hovertemplate: "%{y}<br>%{x}: %{z:,} AI publications<extra></extra>", colorbar: { thickness: 8, len: .7, tickfont: { size: 10 }, title: { text: "Records", font: { size: 10 } } } }],
    layout: { ...baseLayout(theme), margin: { l: 8, r: 10, t: 8, b: 32 }, xaxis: { type: "category", side: "bottom", tickfont: { size: 11 }, automargin: true }, yaxis: { autorange: "reversed", automargin: true, tickfont: { size: 10 } } },
  }), [years, rows]);
  return <PlotlyChart build={build} height={Math.max(260, rows.length * 40 + 70)} ariaLabel="AI publications by research field and year; darker cells indicate more publications" />;
}
