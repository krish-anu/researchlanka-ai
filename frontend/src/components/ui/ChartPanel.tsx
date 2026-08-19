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
      <div className="mb-4 flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h2 className="font-display text-h2 text-ink">{title}</h2>
          {description ? (
            <p className="mt-1 text-body-sm text-ink-secondary">{description}</p>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
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
      className="inline-flex items-center gap-1.5 rounded border border-rule px-2 py-1 text-body-sm text-ink-secondary hover:border-primary hover:text-primary"
    >
      <span aria-hidden>↓</span>
      {children}
    </a>
  );
}

/**
 * Container for AI-synthesised prose. Violet tint plus a machine-tier left rule,
 * so a reader can tell generated text from harvested metadata at a glance.
 */
export function MachinePanel({
  title = "AI summary",
  children,
}: {
  title?: string;
  children: ReactNode;
}) {
  return (
    <section className="machine-panel p-4">
      <h3 className="label-caps text-machine">{title}</h3>
      <div className="mt-2 text-body-sm text-ink-secondary">{children}</div>
    </section>
  );
}
