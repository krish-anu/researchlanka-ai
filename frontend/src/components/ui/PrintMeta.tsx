import { formatSnapshotDate } from "@/components/ui/Provenance";
import { summarizeActiveFilters } from "@/services/printMeta";
import type { SearchParams } from "@/services/filters";

/**
 * Print-only citation header: page title, snapshot date, and active filters.
 * Hidden on screen; shown at the top of printed pages.
 */
export function PrintMeta({
  title,
  snapshotDate,
  searchParams,
  extra,
}: {
  title: string;
  snapshotDate?: string | null;
  searchParams?: SearchParams;
  /** Extra lines (e.g. dataset stage). */
  extra?: string[];
}) {
  const snapshot = formatSnapshotDate(snapshotDate ?? null);
  const filters = searchParams
    ? summarizeActiveFilters(searchParams)
    : null;

  return (
    <header className="print-meta" aria-hidden="true">
      <p className="print-meta-brand">ResearchLanka · Sri Lanka AI research</p>
      <h1 className="print-meta-title">{title}</h1>
      <ul className="print-meta-list">
        {snapshot ? <li>Snapshot: {snapshot}</li> : null}
        {filters ? <li>Filters: {filters}</li> : <li>Filters: none (full selection)</li>}
        {extra?.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </header>
  );
}
