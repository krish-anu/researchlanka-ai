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
  fontFamily: string;
}

const FALLBACK_FONT = '"IBM Plex Sans", system-ui, -apple-system, sans-serif';

const FALLBACK: ChartTheme = {
  ink: "#0d1e25",
  inkSecondary: "#3f484a",
  muted: "#6f797a",
  grid: "#d9ebf5",
  baseline: "#bfc8c9",
  surface: "#ffffff",
  series: ["#6489ba", "#7f5600", "#3d0a33"],
  sequential: "#347d59",
  fontFamily: FALLBACK_FONT,
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
    // Resolved from the body so charts inherit the loaded next/font stack
    // rather than naming a face the browser may not have.
    fontFamily: getComputedStyle(document.body).fontFamily || FALLBACK_FONT,
  };
}

/** Shared layout chrome: recessive grid, no plot frame, ink-token text. */
export function baseLayout(theme: ChartTheme): Record<string, unknown> {
  return {
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    font: {
      family: theme.fontFamily,
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
      tickfont: { color: theme.muted, size: 12 },
      automargin: true,
    },
    yaxis: {
      gridcolor: theme.grid,
      linecolor: theme.baseline,
      zerolinecolor: theme.baseline,
      tickfont: { color: theme.muted, size: 12 },
      automargin: true,
    },
    modebar: { bgcolor: theme.surface, color: theme.muted, activecolor: theme.sequential },
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

/**
 * Time series may zoom in to read a count. Box-zoom, pan, and scroll-zoom stay
 * off; zoom-in, zoom-out, and reset remain, and the chart clamps to the data.
 */
export const BOUNDED_ZOOM_CONFIG: Record<string, unknown> = {
  ...CHART_CONFIG,
  scrollZoom: false,
  doubleClick: "reset",
  modeBarButtonsToRemove: [
    ...(CHART_CONFIG.modeBarButtonsToRemove as string[]),
    "zoom2d",
    "pan2d",
  ],
};

/** Bar charts stay fitted. Zoom and pan are omitted so the axis cannot be dragged off the data. */
export const LOCKED_BAR_CONFIG: Record<string, unknown> = {
  ...CHART_CONFIG,
  scrollZoom: false,
  doubleClick: false,
  modeBarButtonsToRemove: [
    ...(CHART_CONFIG.modeBarButtonsToRemove as string[]),
    "zoom2d",
    "pan2d",
    "zoomIn2d",
    "zoomOut2d",
    "resetScale2d",
  ],
};

/**
 * Panel chrome hierarchy (owned by `ChartPanel`, not Plotly):
 * title → plain subtitle → insight → Chart/Table + download → plot.
 * Keep Plotly top margin tight so the modebar does not compete with that stack.
 */
export const CHART_PANEL_CHROME = {
  /** Prefer one short sentence for `insight`. */
  insightGuidance: "One sentence: what changed, or what to notice first.",
} as const;

/** Sequential heatmap stops — brand greens, not rainbow (colour-blind safer). */
export function sequentialHeatColorscale(theme: ChartTheme): [number, string][] {
  return [
    [0, theme.surface],
    [0.4, theme.grid],
    [0.75, theme.sequential],
    [1, theme.sequential],
  ];
}
