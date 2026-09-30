import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: string;
  /** Denominator or qualifier — dashboards must state what the number is over. */
  caption?: string;
  hint?: ReactNode;
  icon?: ReactNode;
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
  hint,
  icon,
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
        <span className={`text-xs font-medium ${machine ? "text-machine" : "text-muted"}`}>
          {machine ? "AI · " : ""}{label}
        </span>
        {icon ? <span className="stat-icon" aria-hidden="true">{icon}</span> : null}
      </span>
      <span
        className={`stat-value tabular ${
          machine ? "text-machine" : "text-ink"
        }`}
      >
        {value}
      </span>
      {caption ? (
        <span className="text-body-sm text-ink-secondary">{caption}</span>
      ) : null}
      {hint ? <span className="text-body-sm text-muted">{hint}</span> : null}
    </div>
  );
}

export function StatTileGrid({ children }: { children: ReactNode }) {
  return (
    <div className="stat-grid">
      {children}
    </div>
  );
}
