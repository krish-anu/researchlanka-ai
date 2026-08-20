/** Records the app owns itself, because the read-only API has nowhere to put them. */

export interface SavedItem {
  id: string;
  user_id: string;
  publication_key: string;
  title: string;
  /** Free-text note the owner attaches; empty string when none. */
  note: string;
  created_at: string;
}

export type FlagReason =
  | "wrong_metadata"
  | "duplicate_record"
  | "wrong_author"
  | "wrong_institution"
  | "other";

export const FLAG_REASON_LABEL: Record<FlagReason, string> = {
  wrong_metadata: "Metadata is wrong",
  duplicate_record: "Duplicate of another record",
  wrong_author: "Author is misattributed",
  wrong_institution: "Institution is wrong",
  other: "Something else",
};

export type FlagStatus = "open" | "accepted" | "rejected";

export const FLAG_STATUS_LABEL: Record<FlagStatus, string> = {
  open: "Awaiting review",
  accepted: "Accepted",
  rejected: "Rejected",
};

export interface RecordFlag {
  id: string;
  publication_key: string;
  title: string;
  reason: FlagReason;
  detail: string;
  status: FlagStatus;
  reported_by: { id: string; name: string; email: string };
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
  resolution_note: string;
}

/**
 * A duplicate-candidate pair from the entity-resolution model, waiting on a
 * human decision. The pipeline writes these; until it does, the queue is
 * seeded from a fixture so the screen is testable — see `resolution.ts`.
 */
export interface ResolutionCandidate {
  id: string;
  score: number;
  left: ResolutionSide;
  right: ResolutionSide;
  status: "pending" | "merged" | "rejected";
  created_at: string;
  decided_at: string | null;
  decided_by: string | null;
}

export interface ResolutionSide {
  source: string;
  title: string;
  doi: string | null;
  year: number | null;
  authors: string[];
}

export type AuditAction =
  | "flag.accepted"
  | "flag.rejected"
  | "resolution.merged"
  | "resolution.rejected"
  | "user.role_changed"
  | "user.disabled"
  | "user.enabled";

export interface AuditEntry {
  id: string;
  action: AuditAction;
  /** What was acted on — a flag id, candidate id or user id. */
  subject: string;
  summary: string;
  actor: { id: string; name: string };
  created_at: string;
}
