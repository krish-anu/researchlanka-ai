import type { ReactNode } from "react";

interface StatTileProps {
  label: string;
  value: string;
  /** Denominator or qualifier — dashboards must state what the number is over. */
  caption?: string;
  hint?: ReactNode;
}

/**
 * A single headline figure. Deliberately not a chart: one number's job is to be
 * read, not compared, so it gets type scale instead of a plot.
 */
export function StatTile({ label, value, caption, hint }: StatTileProps) {
  return (
    <div className="panel flex flex-col gap-1 p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-muted">
        {label}
      </div>
      <div className="text-3xl font-semibold leading-tight text-ink">{value}</div>
      {caption ? (
        <div className="text-sm text-ink-secondary">{caption}</div>
      ) : null}
      {hint ? <div className="text-xs text-muted">{hint}</div> : null}
    </div>
  );
}

export function StatTileGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {children}
    </div>
  );
}
