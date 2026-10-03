"use client";

import { useEffect, useRef, useState } from "react";

import { CHART_CONFIG, readChartTheme, type ChartTheme } from "./theme";

export type PlotlyPointClick = {
  pointIndex: number;
  curveNumber: number;
  customdata?: unknown;
  label?: string;
  parent?: string;
  currentPath?: string;
};

/** Return `false` to cancel Plotly’s treemap zoom. */
export type PlotlyTreemapClickResult = void | false;

interface PlotlyChartProps {
  /** Builds traces + layout from the resolved theme, so colours follow tokens. */
  build: (theme: ChartTheme) => {
    data: Record<string, unknown>[];
    layout: Record<string, unknown>;
  };
  height?: number;
  /** Described by the surrounding heading; announced for screen readers. */
  ariaLabel: string;
  /** Fired for Plotly `plotly_click` when a data point is selected. */
  onPointClick?: (point: PlotlyPointClick) => void;
  /**
   * Treemap drill. Return `false` to stay on the current mosaic instead of
   * zooming one tile to fill the chart.
   */
  onTreemapClick?: (point: PlotlyPointClick) => PlotlyTreemapClickResult;
  /**
   * When this changes to `""`, animate the treemap back to the root mosaic.
   * A non-empty value is recorded only; the click animation opens that level.
   */
  treemapLevel?: string;
  /** Called after each successful `Plotly.react`, including the first draw. */
  onRender?: () => void;
  /** Plotly config. Bar charts pass the locked config so zoom is unavailable. */
  config?: Record<string, unknown>;
  /** Keep zoom and pan inside these axis ranges. */
  axisClamp?: {
    x?: [number, number];
    y?: [number, number];
  };
  /** Extra class on the plot host. Mosaic charts drop the modebar gutter. */
  hostClassName?: string;
}

type PlotlyModule = typeof import("plotly.js-dist-min")["default"];

function readRange(event: Record<string, unknown>, axis: "xaxis" | "yaxis"): [number, number] | null {
  const packed = event[`${axis}.range`];
  const start = Array.isArray(packed) ? packed[0] : event[`${axis}.range[0]`];
  const end = Array.isArray(packed) ? packed[1] : event[`${axis}.range[1]`];
  const a = Number(start);
  const b = Number(end);
  if (!Number.isFinite(a) || !Number.isFinite(b)) return null;
  return [a, b];
}

/** Pull a zoom back inside the data, and stop a zoom-in that collapses the axis. */
function clampRange(
  range: [number, number],
  bounds: [number, number],
  axis: "xaxis" | "yaxis",
): [number, number] | null {
  const [min, max] = bounds;
  const full = Math.max(max - min, 0);
  const minSpan = Math.max(full * 0.12, axis === "xaxis" ? 1 : 1);
  let lo = Math.min(range[0], range[1]);
  let hi = Math.max(range[0], range[1]);
  if (hi - lo < minSpan) {
    const mid = (lo + hi) / 2;
    lo = mid - minSpan / 2;
    hi = mid + minSpan / 2;
  }
  lo = Math.max(min, lo);
  hi = Math.min(max, hi);
  if (hi - lo < minSpan) {
    if (lo <= min) hi = Math.min(max, min + minSpan);
    else lo = Math.max(min, max - minSpan);
  }
  const unchanged =
    Math.abs(lo - Math.min(range[0], range[1])) < 1e-6 &&
    Math.abs(hi - Math.max(range[0], range[1])) < 1e-6;
  if (unchanged) return null;
  return range[0] <= range[1] ? [lo, hi] : [hi, lo];
}

/**
 * One import promise for the whole app.
 *
 * The bundle is ~4.7MB before compression, so it must be requested once and
 * shared: a page with four charts would otherwise queue four separate module
 * resolutions on mount, and the unmount path used to request it a fifth time
 * just to purge.
 */
let plotlyPromise: Promise<PlotlyModule> | null = null;

function loadPlotly(): Promise<PlotlyModule> {
  plotlyPromise ??= import("plotly.js-dist-min").then((module) => module.default);
  return plotlyPromise;
}

/**
 * Imperative Plotly host.
 *
 * Plotly is loaded lazily on the client only — it is a large bundle and cannot
 * server-render. Two things keep that cost off the critical path: the import is
 * shared process-wide, and it is not requested at all until the chart is within
 * a screen of the viewport, so charts sitting below a long profile page cost
 * nothing to a reader who never scrolls to them.
 *
 * The plot is *updated*, never rebuilt: `Plotly.react` diffs against what is
 * already drawn, so a theme flip or new data reuses the existing canvas and
 * `purge` runs only on unmount.
 */
export function PlotlyChart({
  build,
  height = 280,
  ariaLabel,
  onPointClick,
  onTreemapClick,
  treemapLevel,
  onRender,
  config = CHART_CONFIG,
  axisClamp,
  hostClassName = "",
}: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const clickRef = useRef(onPointClick);
  const treemapRef = useRef(onTreemapClick);
  const renderRef = useRef(onRender);
  const treemapListener = useRef<((event: unknown) => unknown) | null>(null);
  const relayoutListener = useRef<((event: Record<string, unknown>) => void) | null>(null);
  const treemapLevelRef = useRef<string | null>(null);
  const clampRef = useRef(axisClamp);
  clampRef.current = axisClamp;
  clickRef.current = onPointClick;
  treemapRef.current = onTreemapClick;
  renderRef.current = onRender;
  const [failed, setFailed] = useState(false);
  const [ready, setReady] = useState(false);
  const [scheme, setScheme] = useState(0);
  const [visible, setVisible] = useState(false);

  // Defer the whole cost until the chart is nearly on screen. Without
  // IntersectionObserver (older browsers, jsdom) the chart renders immediately
  // rather than never.
  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    if (typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          setVisible(true);
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setScheme((value) => value + 1);
    media.addEventListener("change", onChange);
    window.addEventListener("researchlanka-theme-change", onChange);
    return () => {
      media.removeEventListener("change", onChange);
      window.removeEventListener("researchlanka-theme-change", onChange);
    };
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const element = containerRef.current;
    if (!element) return;

    const readPoint = (event: {
      points?: Array<{
        pointIndex?: number;
        pointNumber?: number;
        curveNumber?: number;
        customdata?: unknown;
        label?: string;
        parent?: string;
        currentPath?: string;
      }>;
    }): PlotlyPointClick | undefined => {
      const point = event.points?.[0];
      if (!point) return undefined;
      return {
        pointIndex: point.pointIndex ?? point.pointNumber ?? 0,
        curveNumber: point.curveNumber ?? 0,
        customdata: point.customdata,
        label: point.label,
        parent: point.parent,
        currentPath: point.currentPath,
      };
    };

    const onClick = (event: Parameters<typeof readPoint>[0]) => {
      const point = readPoint(event);
      if (!point || !clickRef.current) return;
      clickRef.current(point);
    };

    loadPlotly()
      .then((Plotly) => {
        if (cancelled) return;
        const onTreemap = (event: unknown) => {
          const point = readPoint(event as Parameters<typeof readPoint>[0]);
          if (!point || !treemapRef.current) return;
          return treemapRef.current(point);
        };
        const { data, layout } = build(readChartTheme());
        return Promise.resolve(
          Plotly.react(element, data, layout, config),
        ).then(() => {
          if (cancelled) return;
          setReady(true);
          renderRef.current?.();
          const node = element as HTMLElement & {
            on?: (event: string, handler: typeof onClick) => void;
            removeListener?: (event: string, handler: typeof onClick) => void;
          };
          node.removeListener?.("plotly_click", onClick);
          if (treemapListener.current) {
            node.removeListener?.(
              "plotly_treemapclick",
              treemapListener.current as typeof onClick,
            );
          }
          treemapListener.current = onTreemap;
          if (relayoutListener.current) {
            node.removeListener?.(
              "plotly_relayout",
              relayoutListener.current as typeof onClick,
            );
          }
          const onRelayout = (event: Record<string, unknown>) => {
            const clamp = clampRef.current;
            if (!clamp) return;
            const update: Record<string, unknown> = {};
            if (clamp.x) {
              const range = readRange(event, "xaxis");
              const next = range ? clampRange(range, clamp.x, "xaxis") : null;
              if (next) update["xaxis.range"] = next;
            }
            if (clamp.y) {
              const range = readRange(event, "yaxis");
              const next = range ? clampRange(range, clamp.y, "yaxis") : null;
              if (next) update["yaxis.range"] = next;
            }
            if (Object.keys(update).length > 0) {
              const plotly = Plotly as PlotlyModule & {
                relayout: (root: HTMLElement, update: Record<string, unknown>) => Promise<unknown>;
              };
              void plotly.relayout(element, update);
            }
          };
          relayoutListener.current = onRelayout;
          node.on?.("plotly_click", onClick);
          node.on?.("plotly_relayout", onRelayout as typeof onClick);
          node.on?.("plotly_treemapclick", onTreemap);
        });
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
      const node = element as HTMLElement & {
        removeListener?: (event: string, handler: typeof onClick) => void;
      };
      node.removeListener?.("plotly_click", onClick);
      if (treemapListener.current) {
        node.removeListener?.(
          "plotly_treemapclick",
          treemapListener.current as typeof onClick,
        );
      }
      if (relayoutListener.current) {
        node.removeListener?.(
          "plotly_relayout",
          relayoutListener.current as typeof onClick,
        );
      }
    };
  }, [build, config, scheme, visible]);

  useEffect(() => {
    if (!visible || treemapLevel === undefined) return;
    const element = containerRef.current;
    if (!element) return;
    const previous = treemapLevelRef.current;
    treemapLevelRef.current = treemapLevel;
    if (previous === null || previous === treemapLevel || treemapLevel !== "") return;

    let cancelled = false;
    loadPlotly()
      .then((Plotly) => {
        if (cancelled) return;
        const plotly = Plotly as PlotlyModule & {
          restyle: (
            root: HTMLElement,
            update: Record<string, unknown>,
            traces?: number[],
          ) => Promise<unknown>;
        };
        return plotly.restyle(element, { level: [""] }, [0]);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [treemapLevel, visible]);

  // Plotly attaches listeners and a WebGL context, so the node is purged when
  // the component goes away — but only then, since `react` above reuses it.
  useEffect(() => {
    const element = containerRef.current;
    return () => {
      if (!element || !plotlyPromise) return;
      plotlyPromise.then((Plotly) => Plotly.purge(element)).catch(() => undefined);
    };
  }, []);

  if (failed) {
    return (
      <p className="p-4 text-body-sm text-muted">
        The chart library could not be loaded. The underlying numbers are
        available in the table below.
      </p>
    );
  }

  return (
    <div className="chart-scroll">
      <div className={`plotly-host relative min-w-0 ${hostClassName}`.trim()}>
        <div
          ref={containerRef}
          role="img"
          aria-label={ariaLabel}
          aria-busy={!ready}
          style={{ height }}
          className="w-full"
        />
        {!ready ? (
          <div
            className="pointer-events-none absolute inset-0 flex items-center justify-center rounded-lg bg-wash/50 text-body-sm text-muted"
            role="status"
          >
            Loading chart…
          </div>
        ) : null}
      </div>
    </div>
  );
}
