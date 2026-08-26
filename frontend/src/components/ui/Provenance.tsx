interface SourceSpec {
  label: string;
  description: string;
  /** Provenance tier of the design system: one hue per source dataset. */
  token: string;
}

/** Human labels for `source_dataset` values emitted by the pipeline. */
const SOURCE_SPECS: Record<string, SourceSpec> = {
  openalex: {
    label: "OpenAlex",
    description: "Global open bibliographic index.",
    token: "openalex",
  },
  crossref: {
    label: "Crossref",
    description: "DOI registration agency metadata.",
    token: "crossref",
  },
  sljol: {
    label: "SLJOL",
    description: "Sri Lanka Journals Online.",
    token: "sljol",
  },
  local: {
    label: "Local repository",
    description: "Institutional repository harvest.",
    token: "repository",
  },
  repositories: {
    label: "Repository",
    description: "Institutional repository harvest.",
    token: "repository",
  },
  repositories_combined: {
    label: "Repositories",
    description: "Combined institutional repository harvest.",
    token: "repository",
  },
};

/** The datasets consolidated into the corpus, in the footer's stripe order. */
export const CORPUS_SOURCES = [
  "openalex",
  "crossref",
  "sljol",
  "repositories",
] as const;

/** Unknown sources fall back to the neutral provenance hue rather than vanishing. */
export function sourceColor(source: string): string {
  const spec = SOURCE_SPECS[source.toLowerCase()];
  return `var(--src-${spec?.token ?? "other"})`;
}

export function sourceLabel(source: string): string {
  return SOURCE_SPECS[source.toLowerCase()]?.label ?? source;
}

export function SourceDot({ source }: { source: string }) {
  return (
    <span
      aria-hidden
      className="inline-block h-2 w-2 shrink-0 rounded-full"
      style={{ backgroundColor: sourceColor(source) }}
    />
  );
}

export function SourceBadge({ source }: { source: string }) {
  const spec = SOURCE_SPECS[source.toLowerCase()];
  return (
    <span
      title={spec?.description ?? source}
      className="inline-flex items-center gap-1.5 rounded border border-rule bg-surface px-1.5 py-0.5 text-body-sm text-ink-secondary"
    >
      <SourceDot source={source} />
      {spec?.label ?? source}
    </span>
  );
}

/**
 * The signature provenance stripe: a 4px bar segmented by source.
 *
 * Segments are equal width. A record's `source_dataset` list says which
 * datasets it was seen in, not how much each contributed, so weighting the
 * segments would invent a measurement the API never made.
 */
export function ProvenanceStripe({
  sources,
  className = "",
}: {
  sources: string[];
  className?: string;
}) {
  if (sources.length === 0) {
    return (
      <div
        aria-hidden
        className={`h-1 w-full bg-rule ${className}`}
        title="Source not recorded"
      />
    );
  }

  return (
    <div
      aria-hidden
      className={`flex h-1 w-full overflow-hidden ${className}`}
      title={`Sources: ${sources.map(sourceLabel).join(", ")}`}
    >
      {sources.map((source, index) => (
        <div
          key={`${source}-${index}`}
          className="h-full flex-1"
          style={{ backgroundColor: sourceColor(source) }}
        />
      ))}
    </div>
  );
}

/**
 * Every record shows which source(s) it came from — a standing requirement, so
 * an empty provenance list is reported explicitly rather than rendering nothing.
 */
export function ProvenanceList({ sources }: { sources: string[] }) {
  if (sources.length === 0) {
    return <span className="text-body-sm text-muted">Source not recorded</span>;
  }
  return (
    <ul className="flex flex-wrap gap-1" aria-label="Source datasets">
      {sources.map((source) => (
        <li key={source}>
          <SourceBadge source={source} />
        </li>
      ))}
    </ul>
  );
}

/**
 * Dataset vintage disclosure. Analytics figures are counts of *observed*
 * records, never national totals, and the snapshot date must travel with them.
 */
export function SnapshotNote({
  snapshotDate,
  datasetStage,
  className = "",
}: {
  snapshotDate: string | null;
  datasetStage?: string;
  className?: string;
}) {
  return (
    <p className={`text-body-sm text-muted ${className}`}>
      Figures count observed records in the consolidated dataset, not national
      totals.{" "}
      {snapshotDate
        ? `Snapshot: ${new Date(snapshotDate).toLocaleDateString("en-GB", {
            year: "numeric",
            month: "short",
            day: "numeric",
          })}.`
        : "Snapshot date unavailable."}
      {datasetStage ? ` Stage: ${datasetStage}.` : null}
    </p>
  );
}
