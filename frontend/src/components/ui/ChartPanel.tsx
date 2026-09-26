"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { DownloadIcon } from "@/components/layout/NavIcons";
import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Feedback";

/** Common chart body heights used by Suspense fallbacks and loading panels. */
export const CHART_SKELETON_HEIGHT = {
  sm: "h-64",
  md: "h-96",
  lg: "h-80",
  xl: "h-[30rem]",
} as const;

export type ChartSkeletonSize = keyof typeof CHART_SKELETON_HEIGHT;

/**
 * Chart-panel shaped placeholder: same chrome as {@link ChartPanel} so streamed
 * charts do not shift the page when they arrive.
 */
export function ChartSkeleton({
  label = "Loading chart…",
  size = "md",
  className = "",
}: {
  label?: string;
  size?: ChartSkeletonSize;
  className?: string;
}) {
  return (
    <section
      className={`panel chart-panel ${className}`.trim()}
      aria-busy="true"
      aria-live="polite"
    >
      <span className="sr-only">{label}</span>
      <div className="chart-panel-head">
        <div className="flex min-w-0 flex-1 flex-col gap-2">
          <Skeleton className="h-4 w-48 max-w-full" />
          <Skeleton className="h-3 w-72 max-w-full" />
        </div>
        <Skeleton className="h-8 w-28 shrink-0" />
      </div>
      <Skeleton className={`w-full ${CHART_SKELETON_HEIGHT[size]}`} />
    </section>
  );
}

export function ChartPanel({
  title,
  description,
  action,
  children,
  table,
  loading = false,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  table?: ReactNode;
  /** When true, keeps the panel chrome and shows a chart-shaped skeleton body. */
  loading?: boolean;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const id = useId();
  const tableRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (view === "table") {
      tableRef.current?.querySelectorAll("details").forEach((detail) => {
        detail.open = true;
      });
    }
  }, [view]);
  return (
    <section
      className="panel chart-panel"
      aria-labelledby={id}
      aria-busy={loading || undefined}
    >
      <div className="chart-panel-head">
        <div>
          <h2 id={id} className="text-ink">
            {title}
          </h2>
          {description ? (
            <p className="mt-1 text-body-sm text-ink-secondary">{description}</p>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!loading && table ? (
            <div className="chart-segments" aria-label={`${title} view`}>
              <button
                type="button"
                aria-pressed={view === "chart"}
                onClick={() => setView("chart")}
              >
                Chart
              </button>
              <button
                type="button"
                aria-pressed={view === "table"}
                onClick={() => setView("table")}
              >
                Table
              </button>
            </div>
          ) : null}
          {!loading ? action : <Skeleton className="h-8 w-28" />}
        </div>
      </div>
      {loading ? (
        <>
          <span className="sr-only">Loading {title}…</span>
          <Skeleton className={`w-full ${CHART_SKELETON_HEIGHT.md}`} />
        </>
      ) : (
        <>
          {view === "chart" ? children : null}
          {view === "table" ? (
            <div ref={tableRef} className="table-chart-view">
              {table}
            </div>
          ) : null}
        </>
      )}
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
    <Button href={href} variant="secondary" size="sm">
      <DownloadIcon className="h-3.5 w-3.5" />
      {children}
    </Button>
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
