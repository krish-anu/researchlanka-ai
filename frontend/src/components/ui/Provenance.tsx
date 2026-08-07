interface SourceSpec {
  label: string;
  description: string;
}

/** Human labels for `source_dataset` values emitted by the pipeline. */
const SOURCE_SPECS: Record<string, SourceSpec> = {
  openalex: { label: "OpenAlex", description: "Global open bibliographic index." },
  crossref: { label: "Crossref", description: "DOI registration agency metadata." },
  sljol: { label: "SLJOL", description: "Sri Lanka Journals Online." },
  local: { label: "Local repository", description: "Institutional repository harvest." },
  repositories: { label: "Repository", description: "Institutional repository harvest." },
  repositories_combined: {
    label: "Repositories",
    description: "Combined institutional repository harvest.",
  },
};

export function SourceBadge({ source }: { source: string }) {
  const spec = SOURCE_SPECS[source.toLowerCase()];
  return (
    <span
      title={spec?.description ?? source}
      className="inline-flex items-center rounded border border-hairline bg-wash px-1.5 py-0.5 text-xs text-ink-secondary"
    >
      {spec?.label ?? source}
    </span>
  );
}

/**
 * Every record shows which source(s) it came from — a standing requirement, so
 * an empty provenance list is reported explicitly rather than rendering nothing.
 */
export function ProvenanceList({ sources }: { sources: string[] }) {
  if (sources.length === 0) {
    return <span className="text-xs text-muted">Source not recorded</span>;
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
    <p className={`text-xs text-muted ${className}`}>
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
