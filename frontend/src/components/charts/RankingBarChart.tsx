"use client";

import { useCallback, useMemo } from "react";

import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, type ChartTheme } from "./theme";

interface RankingBarChartProps {
  entries: { label: string; value: number }[];
  valueLabel: string;
  ariaLabel: string;
  height?: number;
}

function truncateLabel(label: string, max = 34): string {
  return label.length <= max ? label : `${label.slice(0, max - 1)}…`;
}

/**
 * Ranked magnitude across categories.
 *
 * Horizontal so long institution and field names stay readable. One measure,
 * one hue — rank is already carried by position, so colour is not asked to
 * repeat it. Values are labelled directly at the bar ends, which is also the
 * relief the light-mode palette requires.
 */
export function RankingBarChart({
  entries,
  valueLabel,
  ariaLabel,
  height,
}: RankingBarChartProps) {
  // Plotly draws the first category at the bottom; reverse so rank 1 is on top.
  // Memoised because a fresh array on every render would change `build`, and
  // the chart host reads a new `build` as new data to draw.
  const ordered = useMemo(() => [...entries].reverse(), [entries]);

  const build = useCallback(
    (theme: ChartTheme) => {
      const base = baseLayout(theme);
      return {
        data: [
          {
            type: "bar",
            orientation: "h",
            x: ordered.map((entry) => entry.value),
            y: ordered.map((entry) => truncateLabel(entry.label)),
            marker: {
              color: theme.sequential,
              cornerradius: 4,
            },
            text: ordered.map((entry) => entry.value.toLocaleString("en-GB")),
            textposition: "outside",
            textfont: { color: theme.inkSecondary, size: 11 },
            cliponaxis: false,
            customdata: ordered.map((entry) => entry.label),
            hovertemplate: `%{customdata}<br>${valueLabel}: %{x:,}<extra></extra>`,
          },
        ],
        layout: {
          ...base,
          // ~2px of surface between adjacent bars.
          bargap: 0.35,
          margin: { l: 8, r: 56, t: 8, b: 36 },
          xaxis: {
            ...(base.xaxis as Record<string, unknown>),
            title: { text: valueLabel, font: { color: theme.muted, size: 11 } },
            rangemode: "tozero",
          },
          yaxis: {
            ...(base.yaxis as Record<string, unknown>),
            gridcolor: "rgba(0,0,0,0)",
            ticklabelposition: "outside",
            automargin: true,
          },
        },
      };
    },
    [ordered, valueLabel],
  );

  return (
    <PlotlyChart
      build={build}
      height={height ?? Math.max(200, entries.length * 28 + 60)}
      ariaLabel={ariaLabel}
    />
  );
}
