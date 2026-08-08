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

/**
 * Imperative Plotly host.
 *
 * Plotly is loaded lazily on the client only — it is a large bundle and cannot
 * server-render. The chart re-renders when the OS colour scheme flips so dark
 * mode uses its own validated steps rather than an inverted light palette.
 */
export function PlotlyChart({ build, height = 280, ariaLabel }: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [scheme, setScheme] = useState(0);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setScheme((value) => value + 1);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  useEffect(() => {
    let cancelled = false;
    const element = containerRef.current;
    if (!element) return;

    (async () => {
      try {
        const Plotly = (await import("plotly.js-dist-min")).default;
        if (cancelled) return;
        const { data, layout } = build(readChartTheme());
        await Plotly.react(element, data, layout, CHART_CONFIG);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      // Plotly attaches listeners and a WebGL context; purge on unmount.
      import("plotly.js-dist-min")
        .then((module) => module.default.purge(element))
        .catch(() => undefined);
    };
  }, [build, scheme]);

  if (failed) {
    return (
      <p className="p-4 text-sm text-muted">
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
