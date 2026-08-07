"use client";

/**
 * Chart chrome resolved from the CSS custom properties in `globals.css`, so
 * charts follow the same tokens as the rest of the page and the dark steps are
 * the ones that were validated against the dark surface.
 */
export interface ChartTheme {
  ink: string;
  inkSecondary: string;
  muted: string;
  grid: string;
  baseline: string;
  surface: string;
  series: [string, string, string];
  sequential: string;
}

const FALLBACK: ChartTheme = {
  ink: "#0b0b0b",
  inkSecondary: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  baseline: "#c3c2b7",
  surface: "#fcfcfb",
  series: ["#2a78d6", "#eb6834", "#1baf7a"],
  sequential: "#2a78d6",
};

export function readChartTheme(): ChartTheme {
  if (typeof window === "undefined") return FALLBACK;

  const styles = getComputedStyle(document.documentElement);
  const read = (name: string, fallback: string) =>
    styles.getPropertyValue(name).trim() || fallback;

  return {
    ink: read("--ink", FALLBACK.ink),
    inkSecondary: read("--ink-secondary", FALLBACK.inkSecondary),
    muted: read("--muted", FALLBACK.muted),
    grid: read("--grid", FALLBACK.grid),
    baseline: read("--baseline", FALLBACK.baseline),
    surface: read("--surface", FALLBACK.surface),
    series: [
      read("--series-1", FALLBACK.series[0]),
      read("--series-2", FALLBACK.series[1]),
      read("--series-3", FALLBACK.series[2]),
    ],
    sequential: read("--seq-450", FALLBACK.sequential),
  };
}

/** Shared layout chrome: recessive grid, no plot frame, ink-token text. */
export function baseLayout(theme: ChartTheme): Record<string, unknown> {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {
      family: 'system-ui, -apple-system, "Segoe UI", sans-serif',
      size: 12,
      color: theme.inkSecondary,
    },
    margin: { l: 56, r: 16, t: 8, b: 44 },
    hoverlabel: {
      bgcolor: theme.surface,
      bordercolor: theme.baseline,
      font: { color: theme.ink, size: 12 },
    },
    xaxis: {
      gridcolor: theme.grid,
      linecolor: theme.baseline,
      zerolinecolor: theme.baseline,
      tickfont: { color: theme.muted, size: 11 },
      automargin: true,
    },
    yaxis: {
      gridcolor: theme.grid,
      linecolor: theme.baseline,
      zerolinecolor: theme.baseline,
      tickfont: { color: theme.muted, size: 11 },
      automargin: true,
    },
    showlegend: false,
  };
}

/**
 * `toImage` stays enabled — policymakers need downloadable charts for reports.
 * Everything else that lets a reader silently distort the axes is stripped.
 */
export const CHART_CONFIG: Record<string, unknown> = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: [
    "select2d",
    "lasso2d",
    "autoScale2d",
    "toggleSpikelines",
    "hoverClosestCartesian",
    "hoverCompareCartesian",
  ],
  toImageButtonOptions: { format: "png", scale: 2 },
};
