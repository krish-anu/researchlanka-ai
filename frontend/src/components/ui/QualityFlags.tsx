import type { QualityFlag } from "@/types/api";

type Severity = "neutral" | "warning" | "serious";

interface FlagSpec {
  label: string;
  description: string;
  severity: Severity;
  /** Status colour never carries meaning alone — every flag ships an icon. */
  icon: string;
}

/**
 * Mirrors `serializers.quality_flags`. The requirements call for low-confidence
 * records to be flagged rather than presented as certain, so these render as
 * visible labelled badges, not colour-only dots.
 */
const FLAG_SPECS: Record<QualityFlag, FlagSpec> = {
  missing_doi: {
    label: "No DOI",
    description: "This record has no DOI, so it cannot be linked or matched across sources.",
    severity: "warning",
    icon: "○",
  },
  missing_abstract: {
    label: "No abstract",
    description: "No abstract was captured from any source for this record.",
    severity: "neutral",
    icon: "○",
  },
  missing_institutions: {
    label: "No affiliation",
    description: "No institutional affiliation was recorded, so this record is absent from institution views.",
    severity: "warning",
    icon: "○",
  },
  citation_count_divergence: {
    label: "Citation counts disagree",
    description: "OpenAlex and Crossref report materially different citation counts for this record.",
    severity: "serious",
    icon: "≠",
  },
  reference_count_divergence: {
    label: "Reference counts disagree",
    description: "OpenAlex and Crossref report materially different reference counts for this record.",
    severity: "serious",
    icon: "≠",
  },
  repository_only: {
    label: "Repository-only",
    description: "Seen only in a local repository or SLJOL, with no global index (OpenAlex/Crossref) evidence.",
    severity: "warning",
    icon: "▲",
  },
  no_doi_local_record: {
    label: "Local record, no DOI",
    description: "A local/repository record with no DOI — likely to be a duplicate of an indexed record.",
    severity: "warning",
    icon: "▲",
  },
  topic_model_source: {
    label: "Source-assigned topics",
    description: "Topics and concepts come from source/index classification, not official national categories.",
    severity: "neutral",
    icon: "ⓘ",
  },
};

const SEVERITY_CLASS: Record<Severity, string> = {
  neutral: "border-rule text-ink-secondary",
  warning: "border-warning/50 text-ink-secondary",
  serious: "border-serious/60 text-ink-secondary",
};

const ICON_CLASS: Record<Severity, string> = {
  neutral: "text-muted",
  warning: "text-warning",
  serious: "text-serious",
};

export function QualityFlagBadge({ flag }: { flag: QualityFlag | string }) {
  const spec = FLAG_SPECS[flag as QualityFlag];
  if (!spec) {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-rule px-2 py-0.5 text-body-sm text-ink-secondary">
        {flag}
      </span>
    );
  }
  return (
    <span
      title={spec.description}
      className={`inline-flex items-center gap-1 rounded border px-2 py-0.5 text-body-sm ${SEVERITY_CLASS[spec.severity]}`}
    >
      <span aria-hidden className={ICON_CLASS[spec.severity]}>
        {spec.icon}
      </span>
      {spec.label}
    </span>
  );
}

export function QualityFlagList({
  flags,
  max,
}: {
  flags: (QualityFlag | string)[];
  max?: number;
}) {
  if (flags.length === 0) return null;
  const shown = max ? flags.slice(0, max) : flags;
  const hidden = flags.length - shown.length;

  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Data quality flags">
      {shown.map((flag) => (
        <li key={flag}>
          <QualityFlagBadge flag={flag} />
        </li>
      ))}
      {hidden > 0 ? (
        <li className="self-center text-body-sm text-muted">+{hidden} more</li>
      ) : null}
    </ul>
  );
}

export function describeFlag(flag: QualityFlag | string): string | undefined {
  return FLAG_SPECS[flag as QualityFlag]?.description;
}
