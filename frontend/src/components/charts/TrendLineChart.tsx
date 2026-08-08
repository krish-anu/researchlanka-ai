"use client";

import { useCallback } from "react";

import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, type ChartTheme } from "./theme";

interface TrendLineChartProps {
  points: { key: string | number; value: number }[];
  /** Names the single series; no legend box is drawn for one series. */
  valueLabel: string;
  ariaLabel: string;
  height?: number;
}

/**
 * Change over time, one measure per chart.
 *
 * Publications and citations differ by orders of magnitude, so they are never
 * placed on a shared plot with two y-scales — each gets its own chart with a
 * single axis.
 */
export function TrendLineChart({
  points,
  valueLabel,
  ariaLabel,
  height = 280,
}: TrendLineChartProps) {
  const build = useCallback(
    (theme: ChartTheme) => ({
      data: [
        {
          type: "scatter",
          mode: "lines+markers",
          x: points.map((point) => point.key),
          y: points.map((point) => point.value),
          line: { color: theme.series[0], width: 2, shape: "linear" },
          marker: {
            color: theme.series[0],
            size: 8,
            line: { color: theme.surface, width: 2 },
          },
          hovertemplate: `%{x}<br>${valueLabel}: %{y:,}<extra></extra>`,
          name: valueLabel,
        },
      ],
      layout: {
        ...baseLayout(theme),
        // Crosshair + single tooltip is the default read for a time series.
        hovermode: "x unified",
        xaxis: {
          ...(baseLayout(theme).xaxis as Record<string, unknown>),
          title: { text: "Year", font: { color: theme.muted, size: 11 } },
        },
        yaxis: {
          ...(baseLayout(theme).yaxis as Record<string, unknown>),
          title: { text: valueLabel, font: { color: theme.muted, size: 11 } },
          rangemode: "tozero",
        },
      },
    }),
    [points, valueLabel],
  );

  return <PlotlyChart build={build} height={height} ariaLabel={ariaLabel} />;
}
