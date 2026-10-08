const TONE = {
  pending: "border-warning/45 bg-wash text-ink-secondary",
  changes_requested: "border-warning/45 bg-wash text-ink-secondary",
  approved: "border-good bg-wash text-success-text",
  rejected: "border-rule bg-surface text-serious",
  withdrawn: "border-rule bg-surface text-muted",
} as const;

export type ReviewStatus = keyof typeof TONE;

/** Status chip shared by applications, claims and contributions. */
export function StatusBadge({
  status,
  label,
  className = "",
}: {
  status: ReviewStatus;
  label: string;
  className?: string;
}) {
  return (
    <span className={`label-caps inline-flex items-center rounded border px-2 py-1 ${TONE[status]} ${className}`}>
      {label}
    </span>
  );
}
