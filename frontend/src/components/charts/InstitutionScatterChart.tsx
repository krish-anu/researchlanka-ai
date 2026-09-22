"use client";

import { useCallback } from "react";
import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, type ChartTheme } from "./theme";

export interface InstitutionPoint { label: string; publications: number; openAccessShare: number }
export function InstitutionScatterChart({ points }: { points: InstitutionPoint[] }) {
  const build = useCallback((theme: ChartTheme) => ({
    data: [{ type: "scatter", mode: "markers", x: points.map(p => p.publications), y: points.map(p => p.openAccessShare * 100), customdata: points.map(p => p.label), marker: { color: theme.sequential, size: 16, opacity: .8, line: { color: theme.surface, width: 2 } }, hovertemplate: "%{customdata}<br>%{x:,} AI publications<br>%{y:.1f}% open access<extra></extra>" }],
    layout: { ...baseLayout(theme), xaxis: { title: { text: "AI publications", font: { size: 11 } }, rangemode: "tozero", gridcolor: theme.grid, automargin: true }, yaxis: { title: { text: "Open access share (%)", font: { size: 11 } }, range: [0, 105], gridcolor: theme.grid, automargin: true } },
  }), [points]);
  if (!points.length) return <p className="py-8 text-center text-body-sm text-muted">No institution data in this selection.</p>;
  return <PlotlyChart build={build} height={320} ariaLabel="Institution publication output compared with open access share" />;
}
