import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: string;
  /** Denominator or qualifier — dashboards must state what the number is over. */
  caption?: string;
  hint?: ReactNode;
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
  machine = false,
}: StatTileProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-1 rounded border p-4 text-center ${
        machine
          ? "border-rule bg-machine-container"
          : "border-rule bg-surface"
      }`}
    >
      <span
        className={`label-caps ${machine ? "text-machine" : "text-muted"}`}
      >
        {machine ? "AI · " : ""}
        {label}
      </span>
      <span
        className={`font-display text-h2 font-bold tabular ${
          machine ? "text-machine" : "text-primary"
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
    <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
      {children}
    </div>
  );
}
