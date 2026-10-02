"use client";

import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
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

const ChartTitleLevel = createContext<"h2" | "h3">("h2");

/** Charts nested under a section heading render as h3. */
export function NestedChartTitles({ children }: { children: ReactNode }) {
  return <ChartTitleLevel.Provider value="h3">{children}</ChartTitleLevel.Provider>;
}

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
          <Skeleton className="h-3 w-56 max-w-full" />
        </div>
        <Skeleton className="h-8 w-36 shrink-0" />
      </div>
      <Skeleton className={`w-full ${CHART_SKELETON_HEIGHT[size]}`} />
    </section>
  );
}

/**
 * Unified chart chrome: title → plain subtitle → optional insight → toolbar
 * (Chart/Table + download) → body.
 * Plotly’s modebar stays recessive inside the plot host; panel chrome owns hierarchy.
 */
export function ChartPanel({
  title,
  description,
  insight,
  action,
  children,
  table,
  loading = false,
}: {
  title: string;
  /** Plain-language subtitle (what the chart measures). */
  description?: string;
  /** One-sentence takeaway under the subtitle. */
  insight?: string;
  action?: ReactNode;
  children: ReactNode;
  table?: ReactNode;
  /** When true, keeps the panel chrome and shows a chart-shaped skeleton body. */
  loading?: boolean;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  const id = useId();
  const Title = useContext(ChartTitleLevel);
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
      className="panel chart-panel motion-fade-in"
      aria-labelledby={id}
      aria-busy={loading || undefined}
    >
      <div className="chart-panel-head">
        <div className="chart-panel-copy min-w-0 flex-1">
          <Title id={id} className="text-ink">
            {title}
          </Title>
          {description || insight ? (
            <p className="chart-panel-subtitle">{description || insight}</p>
          ) : null}
        </div>
        <div className="chart-panel-toolbar flex flex-wrap items-center gap-2">
          {!loading && table ? (
            <div className="chart-segments chart-segments-compact" aria-label={`${title} view`}>
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
  className = "",
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={`machine-panel p-4 ${className}`.trim()}
      aria-label={title}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="label-caps text-machine">{title}</h3>
        <span className="label-caps text-machine">Model-generated</span>
      </div>
      <div className="mt-2 text-body-sm text-ink-secondary">{children}</div>
    </section>
  );
}

/** Compact legend: violet chrome means model output, not harvested metadata. */
export function MachineLegend({ className = "" }: { className?: string }) {
  return (
    <p
      className={`machine-legend flex items-start gap-2 text-body-sm text-ink-secondary ${className}`.trim()}
      role="note"
    >
      <span
        className="mt-0.5 inline-block h-3 w-3 shrink-0 rounded-sm bg-machine-container ring-1 ring-machine"
        aria-hidden
      />
      <span>
        <strong className="font-medium text-ink">Violet = model-generated.</strong>{" "}
        Bibliographic fields on the neutral surface are harvested metadata.
      </span>
    </p>
  );
}
