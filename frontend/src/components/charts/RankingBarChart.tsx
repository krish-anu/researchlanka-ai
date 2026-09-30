"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/Feedback";
import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, LOCKED_BAR_CONFIG, type ChartTheme } from "./theme";

export interface RankingBarEntry {
  label: string;
  value: number;
  /** When set, clicking the bar navigates to this profile URL. */
  href?: string;
}

interface RankingBarChartProps {
  entries: RankingBarEntry[];
  valueLabel: string;
  ariaLabel: string;
  height?: number;
  /** Hover line when bars navigate somewhere. */
  clickHint?: string;
  /** When set, an empty chart offers this link to drop the current filters. */
  clearHref?: string;
}

function truncateLabel(label: string, max = 34): string {
  return label.length <= max ? label : `${label.slice(0, max - 1)}…`;
}

/**
 * Ranked magnitude across categories.
 *
 * Horizontal so long institution and field names stay readable. Truncated
 * labels keep the full name in the hover tooltip; optional `href` makes bars
 * clickable into profiles.
 */
export function RankingBarChart({
  entries,
  valueLabel,
  ariaLabel,
  height,
  clickHint = "Click to open profile",
  clearHref,
}: RankingBarChartProps) {
  const router = useRouter();
  const [ascending, setAscending] = useState(false);
  const ordered = useMemo(
    () =>
      [...entries].sort((a, b) =>
        ascending ? b.value - a.value : a.value - b.value,
      ),
    [entries, ascending],
  );
  const clickable = ordered.some((entry) => Boolean(entry.href));

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
            textfont: { color: theme.inkSecondary, size: 12 },
            cliponaxis: false,
            customdata: ordered.map((entry) => [
              entry.label,
              entry.href ?? "",
              entry.label.length > 34 ? "1" : "0",
            ]),
            hovertemplate: clickable
              ? `<b>%{customdata[0]}</b><br>${valueLabel}: %{x:,}<br>${clickHint}<extra></extra>`
              : `<b>%{customdata[0]}</b><br>${valueLabel}: %{x:,}<extra></extra>`,
          },
        ],
        layout: {
          ...base,
          bargap: 0.35,
          margin: { l: 8, r: 56, t: 8, b: 36 },
          xaxis: {
            ...(base.xaxis as Record<string, unknown>),
            title: { text: valueLabel, font: { color: theme.muted, size: 12 } },
            rangemode: "tozero",
            fixedrange: true,
          },
          yaxis: {
            ...(base.yaxis as Record<string, unknown>),
            gridcolor: "rgba(0,0,0,0)",
            ticklabelposition: "outside",
            automargin: true,
            fixedrange: true,
          },
        },
      };
    },
    [ordered, valueLabel, clickable, clickHint],
  );

  if (entries.length === 0) {
    return (
      <EmptyState
        bare
        title="No records in this selection"
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
    <div>
      <div className="mb-2 flex justify-end">
        <Button
          type="button"
          variant="secondary"
          onClick={() => setAscending((value) => !value)}
          aria-label="Toggle ranking order"
        >
          {ascending ? "Lowest first" : "Highest first"} ↕
        </Button>
      </div>
      <PlotlyChart
        build={build}
        height={height ?? Math.max(200, entries.length * 28 + 60)}
        ariaLabel={ariaLabel}
        config={LOCKED_BAR_CONFIG}
        onPointClick={
          clickable
            ? ({ customdata }) => {
              const href = Array.isArray(customdata) ? customdata[1] : "";
              if (typeof href === "string" && href) router.push(href);
            }
            : undefined
        }
      />
    </div>
  );
}
