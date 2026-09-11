"use client";

import { useEffect, useRef, useState } from "react";

import { CHART_CONFIG, readChartTheme, type ChartTheme } from "./theme";

interface PlotlyChartProps {
  /** Builds traces + layout from the resolved theme, so colours follow tokens. */
  build: (theme: ChartTheme) => {
    data: Record<string, unknown>[];
    layout: Record<string, unknown>;
  };
  height?: number;
  /** Described by the surrounding heading; announced for screen readers. */
  ariaLabel: string;
}

type PlotlyModule = typeof import("plotly.js-dist-min")["default"];

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
export function PlotlyChart({ build, height = 280, ariaLabel }: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
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
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    const element = containerRef.current;
    if (!element) return;

    loadPlotly()
      .then((Plotly) => {
        if (cancelled) return;
        const { data, layout } = build(readChartTheme());
        return Plotly.react(element, data, layout, CHART_CONFIG);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });

    return () => {
      cancelled = true;
    };
  }, [build, scheme, visible]);

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
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      style={{ height }}
      className="w-full"
    />
  );
}
