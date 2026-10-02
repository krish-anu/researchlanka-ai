"use client";

import { useRouter } from "next/navigation";
import { useCallback, useMemo } from "react";

import { EmptyState } from "@/components/ui/Feedback";
import { institutionHref } from "@/services/links";
import { PlotlyChart } from "./PlotlyChart";
import { baseLayout, LOCKED_BAR_CONFIG, type ChartTheme } from "./theme";

export interface InstitutionPoint {
  label: string;
  publications: number;
  openAccessShare: number;
  href?: string;
}

/**
 * Output vs open-access share scatter with quadrant labels, explicit size
 * legend, and click-through to institution profiles.
 */
export function InstitutionScatterChart({
  points,
  clearHref,
}: {
  points: InstitutionPoint[];
  clearHref?: string;
}) {
  const router = useRouter();
  const maxPubs = useMemo(
    () => Math.max(...points.map((point) => point.publications), 1),
    [points],
  );
  const midX = useMemo(() => {
    const values = [...points.map((point) => point.publications)].sort(
      (a, b) => a - b,
    );
    const mid = values[Math.floor(values.length / 2)] ?? maxPubs / 2;
    return mid;
  }, [points, maxPubs]);

  const resolved = useMemo(
    () =>
      points.map((point) => ({
        ...point,
        href: point.href ?? institutionHref(point.label),
      })),
    [points],
  );

  const build = useCallback(
    (theme: ChartTheme) => {
      const sizes = resolved.map(
        (point) => 10 + (point.publications / maxPubs) * 22,
      );
      return {
        data: [
          {
            type: "scatter",
            mode: "markers",
            x: resolved.map((point) => point.publications),
            y: resolved.map((point) => point.openAccessShare * 100),
            customdata: resolved.map((point) => [point.label, point.href]),
            marker: {
              color: theme.sequential,
              size: sizes,
              opacity: 0.82,
              line: { color: theme.surface, width: 2 },
              sizemode: "diameter",
            },
            hovertemplate:
              "<b>%{customdata[0]}</b><br>%{x:,} AI publications<br>%{y:.1f}% open access<br>Click to open profile<extra></extra>",
          },
        ],
        layout: {
          ...baseLayout(theme),
          margin: { l: 56, r: 16, t: 36, b: 52 },
          xaxis: {
            title: { text: "AI publications", font: { size: 12 } },
            rangemode: "tozero",
            gridcolor: theme.grid,
            automargin: true,
            fixedrange: true,
            range: [0, maxPubs * 1.08],
          },
          yaxis: {
            title: { text: "Open access share (%)", font: { size: 12 } },
            range: [0, 105],
            gridcolor: theme.grid,
            automargin: true,
            fixedrange: true,
          },
          dragmode: false,
          shapes: [
            {
              type: "line",
              x0: midX,
              x1: midX,
              y0: 0,
              y1: 100,
              line: { color: theme.baseline, width: 1, dash: "dot" },
            },
            {
              type: "line",
              x0: 0,
              x1: maxPubs * 1.05,
              y0: 50,
              y1: 50,
              line: { color: theme.baseline, width: 1, dash: "dot" },
            },
          ],
          annotations: [
            {
              x: midX * 0.35,
              y: 92,
              text: "Lower output · Higher OA",
              showarrow: false,
              font: { size: 12, color: theme.muted },
            },
            {
              x: midX + (maxPubs - midX) * 0.55,
              y: 92,
              text: "Higher output · Higher OA",
              showarrow: false,
              font: { size: 12, color: theme.muted },
            },
            {
              x: midX * 0.35,
              y: 8,
              text: "Lower output · Lower OA",
              showarrow: false,
              font: { size: 12, color: theme.muted },
            },
            {
              x: midX + (maxPubs - midX) * 0.55,
              y: 8,
              text: "Higher output · Lower OA",
              showarrow: false,
              font: { size: 12, color: theme.muted },
            },
          ],
        },
      };
    },
    [resolved, maxPubs, midX],
  );

  if (!points.length) {
    return (
      <EmptyState
        bare
        title="No institution data in this selection"
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
      <PlotlyChart
        build={build}
        height={340}
        ariaLabel="Institution publication output compared with open access share. Click a point to open the institution profile."
        config={LOCKED_BAR_CONFIG}
        onPointClick={({ customdata }) => {
          const href = Array.isArray(customdata) ? customdata[1] : undefined;
          if (typeof href === "string" && href) router.push(href);
        }}
      />
      <p className="mt-2 text-body-sm text-muted">
        Marker size scales with publication count (smallest ≈ fewest on this
        chart; largest ≈ most). Quadrants split at median output and 50% open
        access. Click a point to open that institution’s profile.
      </p>
    </div>
  );
}
