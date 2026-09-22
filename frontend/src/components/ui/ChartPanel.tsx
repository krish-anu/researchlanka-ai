"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { DownloadIcon } from "@/components/layout/NavIcons";

/**
 * Standard chart container: heading, optional action, the plot, and a
 * alternate table of the same numbers.
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
  const [view, setView] = useState<"chart" | "table">("chart");
  const id = useId();
  const tableRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (view === "table") tableRef.current?.querySelectorAll("details").forEach(detail => { detail.open = true; });
  }, [view]);
  return (
    <section className="panel chart-panel" aria-labelledby={id}>
      <div className="chart-panel-head">
        <div>
          <h2 id={id} className="text-ink">{title}</h2>
          {description ? (
            <p className="mt-1 text-body-sm text-ink-secondary">{description}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {table ? <div className="chart-segments" aria-label={`${title} view`}>
            <button type="button" aria-pressed={view === "chart"} onClick={() => setView("chart")}>Chart</button>
            <button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button>
          </div> : null}
          {action}
        </div>
      </div>
      {view === "chart" ? children : null}
      {view === "table" ? <div ref={tableRef} className="table-chart-view">{table}</div> : null}
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
      className="button"
    >
      <DownloadIcon className="h-3.5 w-3.5" />
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
