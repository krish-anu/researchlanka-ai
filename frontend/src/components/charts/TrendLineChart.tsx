"use client";

import { useCallback, useState } from "react";
import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, type ChartTheme } from "./theme";

interface TrendLineChartProps {
  points: { key: string | number; value: number }[];
  valueLabel: string;
  ariaLabel: string;
  height?: number;
  secondary?: { label: string; points: { key: string | number; value: number }[] };
}

export function TrendLineChart({ points, valueLabel, ariaLabel, height = 280, secondary }: TrendLineChartProps) {
  const [style, setStyle] = useState<"area" | "line" | "bar">("area");
  const build = useCallback((theme: ChartTheme) => {
    const base = baseLayout(theme);
    const series = [{ label: valueLabel, points }, ...(secondary ? [secondary] : [])];
    return {
      data: series.map((series, index) => ({
        type: style === "bar" ? "bar" : "scatter",
        ...(style !== "bar" ? { mode: "lines+markers", fill: style === "area" && index === 0 ? "tozeroy" : "none", fillcolor: `${theme.sequential}20` } : {}),
        x: series.points.map(point => point.key), y: series.points.map(point => point.value),
        line: { color: index === 0 ? theme.sequential : theme.series[1], width: 2.5, dash: index === 0 ? "solid" : "dot" },
        marker: { color: index === 0 ? theme.sequential : theme.series[1], size: 7, line: { color: theme.surface, width: 2 }, cornerradius: 4 },
        hovertemplate: `%{x}<br>${series.label}: %{y:,}<extra></extra>`, name: series.label,
      })),
      layout: { ...base, hovermode: "x unified", barmode: "group", showlegend: !!secondary,
        legend: { orientation: "h", y: -0.22, font: { size: 11 } },
        xaxis: { ...(base.xaxis as object), title: { text: "Year", font: { size: 11 } }, dtick: points.length <= 15 ? 1 : undefined },
        yaxis: { ...(base.yaxis as object), title: { text: valueLabel, font: { size: 11 } }, rangemode: "tozero" },
      },
    };
  }, [points, valueLabel, secondary, style]);
  return <div><div className="mb-3 flex justify-end"><div className="chart-segments" aria-label={`${valueLabel} chart style`}>{(["area", "line", "bar"] as const).map(value => <button key={value} type="button" aria-pressed={value === style} onClick={() => setStyle(value)}>{value[0].toUpperCase() + value.slice(1)}</button>)}</div></div><PlotlyChart build={build} height={height} ariaLabel={ariaLabel} /></div>;
}
