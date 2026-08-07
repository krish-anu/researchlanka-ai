import type { ReactNode } from "react";

/**
 * Standard chart container: heading, optional action, the plot, and a
 * collapsed table of the same numbers underneath.
 */
export function ChartPanel({
  title,
  description,
  action,
  children,
  table,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  table?: ReactNode;
}) {
  return (
    <section className="panel p-4">
      <div className="mb-2 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="text-base font-semibold text-ink">{title}</h2>
          {description ? (
            <p className="mt-0.5 text-sm text-ink-secondary">{description}</p>
          ) : null}
        </div>
        {action ? <div className="shrink-0 text-sm">{action}</div> : null}
      </div>
      {children}
      {table}
    </section>
  );
}

export function DownloadLink({
  href,
  children = "Download CSV",
}: {
  href: string;
  children?: ReactNode;
}) {
  return (
    <a
      href={href}
      className="inline-flex items-center gap-1 rounded-md border border-hairline px-2 py-1 text-xs text-ink-secondary hover:bg-wash hover:text-ink"
    >
      <span aria-hidden>↓</span>
      {children}
    </a>
  );
}
