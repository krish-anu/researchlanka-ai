"use client";

import { useCallback } from "react";

import { EmptyState } from "@/components/ui/Feedback";
import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, BOUNDED_ZOOM_CONFIG, type ChartTheme } from "./theme";

interface TrendLineChartProps {
  points: { key: string | number; value: number }[];
  valueLabel: string;
  ariaLabel: string;
  height?: number;
  /** Open-access counts drawn on the same axes as the main series. */
  secondary?: {
    label: string;
    points: { key: string | number; value: number }[];
  };
  clearHref?: string;
}

/**
 * Publication counts over time, with an optional open-access line on the same axes.
 * Zoom in and out stay inside the data range.
 */
export function TrendLineChart({
  points,
  valueLabel,
  ariaLabel,
  height = 280,
  secondary,
  clearHref,
}: TrendLineChartProps) {
  const years = points.map((point) => Number(point.key)).filter(Number.isFinite);
  const yearMin = years.length ? Math.min(...years) : undefined;
  const yearMax = years.length ? Math.max(...years) : undefined;
  const valueMax = Math.max(
    0,
    ...points.map((point) => point.value),
    ...(secondary?.points.map((point) => point.value) ?? []),
  );
  const xClamp: [number, number] | undefined =
    yearMin != null && yearMax != null ? [yearMin - 0.5, yearMax + 0.5] : undefined;
  const yClamp: [number, number] = [0, valueMax === 0 ? 1 : valueMax * 1.08];

  const build = useCallback(
    (theme: ChartTheme) => {
      const base = baseLayout(theme);
      const data: Record<string, unknown>[] = [
        {
          type: "scatter",
          mode: "lines+markers",
          x: points.map((point) => point.key),
          y: points.map((point) => point.value),
          line: { color: theme.sequential, width: 2.5 },
          marker: {
            color: theme.sequential,
            size: 7,
            line: { color: theme.surface, width: 2 },
          },
          hovertemplate: `%{x}<br>${valueLabel}: %{y:,}<extra></extra>`,
          name: valueLabel,
        },
      ];
      if (secondary && secondary.points.length > 0) {
        data.push({
          type: "scatter",
          mode: "lines+markers",
          x: secondary.points.map((point) => point.key),
          y: secondary.points.map((point) => point.value),
          line: { color: theme.series[1], width: 2, dash: "dot" },
          marker: {
            color: theme.series[1],
            size: 6,
            symbol: "diamond",
            line: { color: theme.surface, width: 1 },
          },
          hovertemplate: `%{x}<br>${secondary.label}: %{y:,}<extra></extra>`,
          name: secondary.label,
        });
      }
      return {
        data,
        layout: {
          ...base,
          hovermode: "x unified",
          showlegend: Boolean(secondary?.points.length),
          legend: {
            orientation: "h",
            y: 1.12,
            x: 0,
            font: { size: 12, color: theme.ink },
          },
          xaxis: {
            ...(base.xaxis as object),
            title: { text: "Year", font: { size: 12 } },
            dtick: points.length <= 15 ? 1 : undefined,
            range: xClamp,
            fixedrange: false,
          },
          yaxis: {
            ...(base.yaxis as object),
            title: { text: valueLabel, font: { size: 12 } },
            rangemode: "tozero",
            range: yClamp,
            fixedrange: false,
          },
          margin: { l: 48, r: 16, t: secondary?.points.length ? 36 : 12, b: 40 },
        },
      };
    },
    [points, secondary, valueLabel, xClamp, yClamp],
  );

  if (points.length === 0) {
    return (
      <EmptyState
        bare
        title="No annual counts in this selection"
        description={
          clearHref
            ? "Try removing a year or field filter to widen the results."
            : undefined
        }
        recovery={
          clearHref ? { kind: "clear-filters", href: clearHref } : undefined
        }
      />
    );
  }

  return (
    <PlotlyChart
      build={build}
      height={height}
      ariaLabel={ariaLabel}
      config={BOUNDED_ZOOM_CONFIG}
      axisClamp={{ x: xClamp, y: yClamp }}
    />
  );
}
