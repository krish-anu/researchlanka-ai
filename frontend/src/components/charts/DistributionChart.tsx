"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { PlotlyChart, type PlotlyPointClick } from "./PlotlyChart";
import { RankingBarChart } from "./RankingBarChart";
import { baseLayout, type ChartTheme } from "./theme";

export interface MosaicEntry {
  label: string;
  value: number;
}

/** Keep in step with mosaic-leave / mosaic-enter durations in globals.css. */
const LEAVE_MS = 180;
const ENTER_MS = 460;

type Phase = "idle" | "out" | "hold" | "in";
type Direction = "deeper" | "back";

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * Category composition: mosaic (treemap) by default, with horizontal bars for
 * count comparison. When `branches` are provided, choosing a parent opens its
 * children in the same mosaic. The outgoing layer leaves upward; a deeper
 * layer enters from below, and the parent returns from above.
 */
export function DistributionChart({
  entries,
  ariaLabel,
  initialView = "mosaic",
  branches = {},
}: {
  entries: MosaicEntry[];
  ariaLabel: string;
  initialView?: "mosaic" | "bar";
  /** Child slices keyed by parent label. */
  branches?: Record<string, MosaicEntry[]>;
}) {
  const [view, setView] = useState<"mosaic" | "bar">(
    initialView === "bar" ? "bar" : "mosaic",
  );
  const [focus, setFocus] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [direction, setDirection] = useState<Direction>("deeper");
  const pending = useRef<string | null>(null);

  const focused = focus ? (branches[focus] ?? []).filter((child) => child.value > 0) : [];
  const shown = focused.length > 0 ? focused : entries;
  const canDrill = Object.values(branches).some((items) =>
    items.some((child) => child.value > 0),
  );
  const moving = phase !== "idle";

  const go = useCallback((next: string | null) => {
    if (next === focus || phase !== "idle") return;
    if (prefersReducedMotion()) {
      setFocus(next);
      return;
    }
    pending.current = next;
    setDirection(next ? "deeper" : "back");
    setPhase("out");
  }, [focus, phase]);

  useEffect(() => {
    if (phase !== "out") return;
    const id = window.setTimeout(() => {
      setFocus(pending.current);
      setPhase("hold");
    }, LEAVE_MS);
    return () => window.clearTimeout(id);
  }, [phase]);

  useEffect(() => {
    if (phase !== "hold") return;
    const id = window.setTimeout(() => setPhase("in"), 70);
    return () => window.clearTimeout(id);
  }, [phase]);

  const onChartRender = useCallback(() => {
    setPhase((current) => (current === "hold" ? "in" : current));
  }, []);

  useEffect(() => {
    if (phase !== "in") return;
    const id = window.setTimeout(() => setPhase("idle"), ENTER_MS);
    return () => window.clearTimeout(id);
  }, [phase]);

  const build = useCallback(
    (theme: ChartTheme) => {
      const palette = [
        theme.sequential,
        theme.series[1],
        theme.series[0],
        theme.series[2],
        theme.muted,
        theme.baseline,
      ];
      const labels = shown.map((entry) => entry.label);
      const values = shown.map((entry) => entry.value);
      return {
        data: [
          {
            type: "treemap",
            ids: labels,
            labels,
            parents: labels.map(() => ""),
            values,
            level: "",
            textinfo: "label+value+percent root",
            marker: {
              colors: shown.map((_, index) => palette[index % palette.length]),
              line: { color: theme.surface, width: 3 },
            },
            tiling: { packing: "squarify" },
            pathbar: { visible: false },
            hovertemplate:
              "%{label}<br>%{value:,} publications (%{percentRoot})<extra></extra>",
          },
        ],
        layout: {
          ...baseLayout(theme),
          margin: { l: 0, r: 0, t: 0, b: 0 },
          showlegend: false,
          uirevision: focus ?? "fields",
        },
      };
    },
    [focus, shown],
  );

  const onTreemapClick = useCallback(
    (point: PlotlyPointClick) => {
      if (phase !== "idle") return false;
      if (focus) return undefined;
      const path = String(point.currentPath ?? "")
        .split("/")
        .filter(Boolean);
      const custom = Array.isArray(point.customdata) ? point.customdata : [];
      const label = String(custom[0] ?? point.label ?? path.at(-1) ?? "");
      if ((branches[label] ?? []).some((child) => child.value > 0)) {
        go(label);
        return false;
      }
      return undefined;
    },
    [branches, focus, go, phase],
  );

  return (
    <div>
      <div className="mb-1 flex justify-end">
        <div className="chart-segments chart-segments-compact" aria-label="Distribution chart style">
          <button
            type="button"
            aria-pressed={view === "mosaic"}
            onClick={() => setView("mosaic")}
          >
            Mosaic
          </button>
          <button
            type="button"
            aria-pressed={view === "bar"}
            onClick={() => setView("bar")}
          >
            Counts
          </button>
        </div>
      </div>
      <div className="mosaic-stage" data-phase={phase} data-dir={direction}>
        {focus ? (
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <Button
              type="button"
              variant="secondary"
              size="sm"
              disabled={moving}
              onClick={() => go(null)}
            >
              ← All fields
            </Button>
            <p className="text-body-sm font-medium text-ink" aria-live="polite">
              {focus}
            </p>
          </div>
        ) : null}
        {view === "bar" ? (
          <RankingBarChart
            entries={
              focus && (branches[focus]?.length ?? 0) > 0 ? branches[focus] : entries
            }
            valueLabel="AI publications"
            ariaLabel={ariaLabel}
          />
        ) : (
          <div className="min-w-0">
            <PlotlyChart
              build={build}
              height={360}
              hostClassName="plotly-host-fill"
              ariaLabel={
                focus
                  ? `Subfields of ${focus}. Use All fields to return to the field mosaic.`
                  : ariaLabel
              }
              onTreemapClick={canDrill ? onTreemapClick : undefined}
              onRender={onChartRender}
            />
          </div>
        )}
      </div>
    </div>
  );
}
