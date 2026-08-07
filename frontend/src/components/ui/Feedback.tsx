import type { ReactNode } from "react";

import { API_BASE_URL, type ApiFailure } from "@/services/api";

/**
 * Explains an API failure without pretending the data is merely empty.
 *
 * The backend needs PostgreSQL with a loaded `final_publications` table, so
 * "unreachable" is the common case during frontend-only development and the
 * panel tells the reader how to start it rather than showing a bare error.
 */
export function ApiErrorPanel({
  error,
  what = "this data",
}: {
  error: ApiFailure;
  what?: string;
}) {
  const isUnreachable = error.code === "unreachable" || error.code === "timeout";

  return (
    <div className="panel border-serious/40 p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold text-ink">
        <span aria-hidden className="text-serious">
          ▲
        </span>
        Could not load {what}
      </h2>
      <p className="mt-2 text-sm text-ink-secondary">{error.message}</p>

      {isUnreachable ? (
        <div className="mt-3 space-y-2 text-sm text-ink-secondary">
          <p>
            This app reads the ResearchLanka API at{" "}
            <code className="rounded bg-wash px-1 py-0.5 text-xs">
              {API_BASE_URL}
            </code>
            . Start it from the repository root:
          </p>
          <pre className="scroll-x rounded-md bg-wash p-3 text-xs">
            <code>cd backend{"\n"}python -m src.api.server --port 8080</code>
          </pre>
          <p className="text-xs text-muted">
            The API queries PostgreSQL, so the database must be running with the
            <code className="mx-1 rounded bg-wash px-1 py-0.5">
              final_publications
            </code>
            table loaded.
          </p>
        </div>
      ) : (
        <p className="mt-3 text-xs text-muted">
          Error code: <code className="rounded bg-wash px-1 py-0.5">{error.code}</code>
          {error.status ? ` (HTTP ${error.status})` : null}
        </p>
      )}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="panel flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="text-base font-medium text-ink">{title}</p>
      {description ? (
        <p className="max-w-prose text-sm text-ink-secondary">{description}</p>
      ) : null}
      {action}
    </div>
  );
}

export function SectionHeading({
  title,
  description,
  action,
}: {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 className="text-lg font-semibold text-ink">{title}</h2>
        {description ? (
          <p className="mt-0.5 text-sm text-ink-secondary">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className = "h-40" }: { className?: string }) {
  return (
    <div
      className={`panel animate-pulse bg-wash ${className}`}
      aria-hidden
      role="presentation"
    />
  );
}
