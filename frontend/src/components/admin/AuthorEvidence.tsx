import type { ReactNode } from "react";

import type { NameMatch } from "@/types/authors";

const TONE = {
  good: "border-good text-success-text",
  warn: "border-warning/60 text-ink-secondary",
  bad: "border-serious/60 text-serious",
  neutral: "border-rule text-muted",
} as const;

/** One verification signal on a review card. */
export function EvidenceChip({
  tone,
  children,
}: {
  tone: keyof typeof TONE;
  children: ReactNode;
}) {
  return (
    <span className={`inline-flex items-center rounded border bg-surface px-2 py-0.5 text-label ${TONE[tone]}`}>
      {children}
    </span>
  );
}

export function NameMatchChip({ match }: { match: NameMatch | undefined }) {
  if (match === "exact") return <EvidenceChip tone="good">Name matches exactly</EvidenceChip>;
  if (match === "initials") return <EvidenceChip tone="warn">Name matches by initials</EvidenceChip>;
  return <EvidenceChip tone="bad">Name does not match</EvidenceChip>;
}

export const EMAIL_KIND_LABEL = {
  academic: "Academic domain",
  sri_lankan_organisation: "Sri Lankan organisation domain",
  free_webmail: "Free webmail",
  other: "Other domain",
  unknown: "Unknown domain",
} as const;
