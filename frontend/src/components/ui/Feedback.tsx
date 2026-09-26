import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { RetryButton } from "@/components/ui/RetryButton";
import { API_BASE_URL, type ApiFailure, type QueryParams } from "@/services/api";
import { hasFacetFilters } from "@/services/filters";

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
    <div className="panel border-l-[3px] border-l-serious p-5">
      <h2 className="flex items-center gap-2 font-display text-h3 text-ink">
        <span aria-hidden className="text-serious">
          ▲
        </span>
        Could not load {what}
      </h2>
      <p className="mt-2 text-body-sm text-ink-secondary">{error.message}</p>

      {isUnreachable ? (
        <div className="mt-3 space-y-2 text-body-sm text-ink-secondary">
          <p>
            This app reads the ResearchLanka API at{" "}
            <code className="data-mono rounded bg-sunk px-1 py-0.5">
              {API_BASE_URL}
            </code>
            . Start it from the repository root:
          </p>
          <pre className="scroll-x rounded bg-sunk p-3">
            <code className="data-mono">
              cd backend{"\n"}python -m src.api.server --port 8080
            </code>
          </pre>
          <p className="text-body-sm text-muted">
            The API queries PostgreSQL, so the database must be running with the
            <code className="data-mono mx-1 rounded bg-sunk px-1 py-0.5">
              final_publications
            </code>
            table loaded.
          </p>
        </div>
      ) : (
        <p className="mt-3 text-body-sm text-muted">
          Error code:{" "}
          <code className="data-mono rounded bg-sunk px-1 py-0.5">{error.code}</code>
          {error.status ? ` (HTTP ${error.status})` : null}
        </p>
      )}

      <div className="mt-4">
        <RetryButton />
      </div>
    </div>
  );
}

/** Primary empty-list recovery: Clear filters vs Browse all. */
export type EmptyRecovery =
  | { kind: "clear-filters"; href: string }
  | { kind: "browse-all"; href: string };

/**
 * Pick the recovery CTA for a zero-result list.
 * Facet/range filters → Clear filters; search-only → Browse all.
 */
export function emptyListRecovery(
  basePath: string,
  filters: QueryParams,
): EmptyRecovery | undefined {
  if (hasFacetFilters(filters)) {
    return { kind: "clear-filters", href: basePath };
  }
  if (typeof filters.q === "string" && filters.q) {
    return { kind: "browse-all", href: basePath };
  }
  return undefined;
}

/** Standard empty-list title, description, and recovery for directory pages. */
export function emptyListState(
  entity: string,
  basePath: string,
  filters: QueryParams,
): {
  title: string;
  description: string;
  recovery: EmptyRecovery | undefined;
} {
  const query = typeof filters.q === "string" ? filters.q : "";
  const recovery = emptyListRecovery(basePath, filters);

  if (query && !hasFacetFilters(filters)) {
    return {
      title: `No ${entity} match this search`,
      description: `Try a broader term, or browse the full ${entity} list.`,
      recovery,
    };
  }

  if (hasFacetFilters(filters)) {
    return {
      title: `No ${entity} match these filters`,
      description: "Try removing a year or field filter to widen the results.",
      recovery,
    };
  }

  return {
    title: `No ${entity} found`,
    description: `No ${entity} are available in this dataset.`,
    recovery,
  };
}

export function EmptyState({
  title,
  description,
  recovery,
  action,
}: {
  title: string;
  description?: string;
  recovery?: EmptyRecovery;
  action?: ReactNode;
}) {
  const recoveryLabel =
    recovery?.kind === "clear-filters"
      ? "Clear filters"
      : recovery?.kind === "browse-all"
        ? "Browse all"
        : null;

  return (
    <div className="panel flex flex-col items-center gap-2 px-6 py-12 text-center">
      <p className="font-display text-h3 text-ink">{title}</p>
      {description ? (
        <p className="max-w-prose text-body-sm text-ink-secondary">{description}</p>
      ) : null}
      {recovery && recoveryLabel ? (
        <Button href={recovery.href} variant="primary" size="sm" className="mt-2">
          {recoveryLabel}
        </Button>
      ) : (
        action
      )}
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
    <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h2 className="font-display text-h2 text-ink">{title}</h2>
        {description ? (
          <p className="mt-1 text-body-sm text-ink-secondary">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function Skeleton({ className = "h-40" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded border border-rule bg-sunk ${className}`}
      aria-hidden
      role="presentation"
    />
  );
}

/**
 * Non-chart panel placeholder (tables, lists). Keeps panel chrome so layout
 * does not jump when the real section streams in.
 */
export function PanelSkeleton({
  label = "Loading…",
  bodyClassName = "h-60",
}: {
  label?: string;
  bodyClassName?: string;
}) {
  return (
    <section className="panel p-5" aria-busy="true" aria-live="polite">
      <span className="sr-only">{label}</span>
      <Skeleton className="mb-4 h-4 w-48" />
      <Skeleton className={`w-full ${bodyClassName}`} />
    </section>
  );
}
