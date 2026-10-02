import Link from "next/link";
import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: string;
  /** Denominator or qualifier — dashboards must state what the number is over. */
  caption?: string;
  /** Secondary line under the value (e.g. absolute count for a share). */
  detail?: string;
  hint?: ReactNode;
  icon?: ReactNode;
  /** Optional mini sparkline (e.g. publications over time). */
  spark?: ReactNode;
  /**
   * Marks the figure as AI-synthesised. The design system reserves the violet
   * machine tier for generated content so it is never read as verified metadata.
   */
  machine?: boolean;
}

/**
 * A single headline figure. Deliberately not a chart: one number's job is to be
 * read, not compared, so it gets type scale instead of a plot.
 */
export function StatTile({
  label,
  value,
  caption,
  detail,
  hint,
  icon,
  spark,
  machine = false,
}: StatTileProps) {
  return (
    <div
      className={`stat-tile ${
        machine
          ? "border-rule bg-machine-container"
          : "border-rule bg-surface"
      }`}
    >
      <span className="flex items-start justify-between gap-3">
        <span className={`text-label font-medium ${machine ? "text-machine" : "text-muted"}`}>
          {machine ? "AI · " : ""}
          {label}
        </span>
        {icon ? <span className="stat-icon" aria-hidden="true">{icon}</span> : null}
      </span>
      <span className="stat-value-row">
        <span
          className={`stat-value tabular ${
            machine ? "text-machine" : "text-ink"
          }`}
        >
          {value}
        </span>
        {spark}
      </span>
      {detail ? (
        <span className="text-body-sm tabular text-ink-secondary">{detail}</span>
      ) : null}
      {caption ? (
        <span className="text-body-sm text-ink-secondary">{caption}</span>
      ) : null}
      {hint ? <span className="text-body-sm text-muted">{hint}</span> : null}
    </div>
  );
}

export function StatTileGrid({
  children,
  asOf,
}: {
  children: ReactNode;
  /** Shared “As of …” subtitle above the tile row (snapshot date). */
  asOf?: string | null;
}) {
  return (
    <div className="stat-grid-block">
      {asOf ? <p className="stat-grid-asof">As of {asOf}</p> : null}
      <div className="stat-grid">{children}</div>
    </div>
  );
}

/**
 * Compact trend spark linking to a fuller chart (overview KPI → trend section).
 */
export function TrendSparkline({
  values,
  href,
  label,
}: {
  values: number[];
  href: string;
  label: string;
}) {
  if (values.length < 2) return null;

  const width = 72;
  const height = 28;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width;
      const y = height - ((value - min) / range) * (height - 4) - 2;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <Link href={href} className="stat-spark" aria-label={label} scroll>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        aria-hidden
      >
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
          strokeLinecap="round"
          points={points}
        />
      </svg>
    </Link>
  );
}
