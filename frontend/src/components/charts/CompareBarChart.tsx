"use client";

import { useCallback } from "react";

import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, type ChartTheme } from "./theme";

interface CompareBarChartProps {
  /** At most 3 entries — the validated all-pairs cap for this palette. */
  entries: { label: string; value: number }[];
  valueLabel: string;
  ariaLabel: string;
  height?: number;
}

/**
 * Head-to-head comparison on a single measure.
 *
 * Each institution keeps the same colour slot across every compare chart, so
 * identity travels with the entity rather than with its current rank. One
 * measure per chart — publications and citations never share an axis.
 *
 * Every bar is directly labelled: slot 3 sits below 3:1 on the light surface,
 * and the relief rule requires labels or a table (this ships both).
 */
export function CompareBarChart({
  entries,
  valueLabel,
  ariaLabel,
  height = 240,
}: CompareBarChartProps) {
  const build = useCallback(
    (theme: ChartTheme) => {
      const base = baseLayout(theme);
      return {
        data: entries.map((entry, index) => ({
          type: "bar",
          name: entry.label,
          x: [entry.label],
          y: [entry.value],
          marker: {
            color: theme.series[index % theme.series.length],
            cornerradius: 4,
          },
          text: [entry.value.toLocaleString("en-GB")],
          textposition: "outside",
          textfont: { color: theme.inkSecondary, size: 12 },
          cliponaxis: false,
          hovertemplate: `%{x}<br>${valueLabel}: %{y:,}<extra></extra>`,
        })),
        layout: {
          ...base,
          bargap: 0.45,
          // Two or more series always carry a legend; identity is never colour alone.
          showlegend: true,
          legend: {
            orientation: "h",
            y: -0.2,
            font: { color: theme.inkSecondary, size: 11 },
          },
          margin: { l: 56, r: 16, t: 16, b: 24 },
          xaxis: {
            ...(base.xaxis as Record<string, unknown>),
            showticklabels: false,
            gridcolor: "rgba(0,0,0,0)",
          },
          yaxis: {
            ...(base.yaxis as Record<string, unknown>),
            title: { text: valueLabel, font: { color: theme.muted, size: 11 } },
            rangemode: "tozero",
          },
        },
      };
    },
    [entries, valueLabel],
  );

  return <PlotlyChart build={build} height={height} ariaLabel={ariaLabel} />;
}
