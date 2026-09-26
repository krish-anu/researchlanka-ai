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

export type FeedbackReason =
  | "incorrect_ai_classification"
  | "incorrect_author"
  | "incorrect_institution"
  | "duplicate_publication"
  | "missing_publication";

export const FEEDBACK_REASON_LABEL: Record<FeedbackReason, string> = {
  incorrect_ai_classification: "Report incorrect AI classification",
  incorrect_author: "Report incorrect author",
  incorrect_institution: "Report incorrect institution",
  duplicate_publication: "Report duplicate publication",
  missing_publication: "Report missing publication",
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

export type AIReviewDecisionLabel = "AI" | "NON_AI";

export interface AIReviewDecision {
  id: string;
  publication_id: string;
  source_row: string;
  decision: AIReviewDecisionLabel;
  note: string;
  decided_at: string;
  decided_by: string;
}

export interface AIReviewCandidate {
  publication_key: string;
  record_version: number;
  review_status:
    | "pending_review"
    | "auto_accepted"
    | "human_accepted"
    | "human_rejected";
  acceptance_method: "auto" | "human" | null;
  assigned_reviewer: { id: string | null; email: string | null; name: string | null };
  decided_by: { id: string | null; email: string | null; name: string | null };
  reviewer_notes: string;
  decision_timestamp: string | null;
  sync_status: "not_queued" | "pending" | "succeeded" | "failed";
  sync_attempt_count: number;
  last_sync_error: string | null;
  last_synced_at: string | null;
  gemini: {
    label: string | null;
    confidence: string | null;
    normalized_label: string | null;
    normalized_confidence: string | null;
    model: string | null;
    reason: string | null;
  };
  publication: {
    title: string | null;
    abstract: string | null;
    keywords: string | null;
    authors: string | null;
    author_affiliations: string | null;
    institutions: string | null;
    sri_lankan_institutions: string | null;
    countries: string | null;
    publication_year: number | null;
    publication_date: string | null;
    type: string | null;
    journal: string | null;
    publisher: string | null;
    doi: string | null;
    url: string | null;
    openalex_id: string | null;
    source_dataset: string | null;
    source_record_id: string | null;
    source_datestamp: string | null;
    language: string | null;
    oa_status: string | null;
    license: string | null;
    volume: string | null;
    issue: string | null;
    first_page: string | null;
    last_page: string | null;
    article_number: string | null;
  };
}

export type AuditAction =
  | "flag.accepted"
  | "flag.rejected"
  | "resolution.merged"
  | "resolution.rejected"
  | "ai_review.ai"
  | "ai_review.non_ai"
  | "pipeline.incremental_started"
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
