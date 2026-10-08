/**
 * Author profiles, claims and contributions — the shapes the backend's
 * `/author`, `/admin/authors` and `/researchers/profiles` endpoints return.
 * See backend/src/api/services/author_profiles.py.
 */

export type ProfileStatus = "pending" | "changes_requested" | "approved" | "rejected";
export type ClaimStatus = "pending" | "approved" | "rejected";
export type ContributionStatus = "pending" | "approved" | "rejected" | "withdrawn";
export type ContributionType = "publication_edit" | "new_publication";
export type NameMatch = "exact" | "initials" | "none";

export const PROFILE_STATUS_LABEL: Record<ProfileStatus, string> = {
  pending: "Waiting for review",
  changes_requested: "Changes requested",
  approved: "Approved",
  rejected: "Not approved",
};

export const CLAIM_STATUS_LABEL: Record<ClaimStatus, string> = {
  pending: "Waiting for review",
  approved: "Approved",
  rejected: "Not approved",
};

export const CONTRIBUTION_STATUS_LABEL: Record<ContributionStatus, string> = {
  pending: "Waiting for review",
  approved: "Approved",
  rejected: "Not approved",
  withdrawn: "Withdrawn",
};

export const CONTRIBUTION_TYPE_LABEL: Record<ContributionType, string> = {
  publication_edit: "Edit to a publication",
  new_publication: "New publication",
};

export interface ProfileLinks {
  website_url: string | null;
  google_scholar_url: string | null;
  researchgate_url: string | null;
  linkedin_url: string | null;
}

export const PROFILE_LINK_LABEL: Record<keyof ProfileLinks, string> = {
  website_url: "Website",
  google_scholar_url: "Google Scholar",
  researchgate_url: "ResearchGate",
  linkedin_url: "LinkedIn",
};

interface ProfileBase {
  profile_id: string;
  slug: string;
  display_name: string;
  name_variants: string[];
  orcid: string | null;
  institution: string;
  department: string;
  position_title: string;
  bio: string;
  links: ProfileLinks;
  status: ProfileStatus;
}

/** One period at one institution, as the author describes their career. */
export interface Affiliation {
  institution: string;
  department: string;
  position_title: string;
  start_year: number | null;
  /** null while the author is still there. */
  end_year: number | null;
}

/** The owner's and administrators' view, with the application fields. */
export interface AuthorProfile extends ProfileBase {
  user_id: string;
  user_email: string;
  application_note: string;
  decision_reason: string;
  decided_by: string | null;
  decided_at: string | null;
  record_version: number;
  submitted_at: string;
  created_at: string;
  updated_at: string;
  /** Present on the owner's workspace. */
  affiliations?: Affiliation[];
}

export interface ProfileStats {
  publication_count: number;
  year_min: number | null;
  year_max: number | null;
  citation_total: number;
}

export interface InstitutionPeriod {
  institution: string;
  publication_count: number;
  year_min: number | null;
  year_max: number | null;
}

/** What anyone can see once a profile is approved. */
export interface PublicAuthorProfile extends ProfileBase {
  verified_at: string | null;
  stats: ProfileStats;
  listed_names?: string[];
  listed_name_counts?: { name_as_listed: string; publication_count: number }[];
  affiliations?: Affiliation[];
  /** Publications by the institution the author was at for each one. */
  institution_breakdown?: { institutions: InstitutionPeriod[]; unattributed: number };
  /** Set when profiles are looked up for a printed name. */
  match?: "claimed" | "similar";
  claimed_count?: number;
}

export interface PublicationClaim {
  claim_id: string;
  profile_id: string;
  publication_key: string;
  name_as_listed: string;
  author_position: number | null;
  status: ClaimStatus;
  decision_reason: string;
  decided_at: string | null;
  created_at: string;
  publication: {
    title: string | null;
    publication_year: number | null;
    is_public: boolean;
  };
}

export interface ClaimEvidence {
  name_match: NameMatch;
  still_listed: boolean;
  orcid_match: boolean;
  competing_claims: { claim_id: string; display_name: string; status: ClaimStatus }[];
}

export interface ReviewedClaim extends PublicationClaim {
  evidence: ClaimEvidence;
  profile?: {
    display_name: string | null;
    slug: string | null;
    institution: string | null;
    orcid: string | null;
  };
}

export type EditableField =
  | "title"
  | "abstract"
  | "keywords"
  | "publication_year"
  | "type"
  | "journal"
  | "publisher"
  | "volume"
  | "issue"
  | "first_page"
  | "last_page"
  | "language"
  | "url"
  | "pdf_url";

export interface CategorySuggestion {
  field: string | null;
  subfield: string | null;
  available: boolean;
  reason: string | null;
}

export interface ClassifierResult {
  label?: "AI" | "non-AI" | "review";
  confidence?: string | null;
  model?: string | null;
  reason?: string | null;
  available?: boolean;
  category?: CategorySuggestion;
}

export interface SubmissionAuthor {
  name: string;
  /** Department or other detail; the institution is separate. */
  affiliation: string;
  /** The institution this author was at for this publication. */
  institution: string;
  country_code: string | null;
  /** A verified ResearchLanka profile this author is linked to. */
  profile_slug: string | null;
  profile_display_name?: string | null;
  is_submitter: boolean;
}

export interface LookupCategory {
  primary_field?: string | null;
  primary_subfield?: string | null;
  primary_domain?: string | null;
  primary_topic?: string | null;
  topics?: string | null;
  concepts?: string | null;
}

export interface NewPublicationProposal {
  doi: string | null;
  title: string;
  abstract: string;
  keywords: string;
  publication_year: number;
  publication_date: string | null;
  type: string;
  journal: string;
  publisher: string;
  volume: string;
  issue: string;
  first_page: string;
  last_page: string;
  language: string;
  url: string | null;
  pdf_url: string | null;
  authors: SubmissionAuthor[];
  your_author_name: string;
  primary_field?: string;
  primary_subfield?: string;
}

export interface OwnershipEvidence {
  ownership_decision?: string | null;
  ownership_class?: string | null;
  ownership_confidence?: string | null;
  ownership_reason?: string | null;
  ownership_evidence?: string | null;
  lead_country?: string | null;
  corresponding_author_countries?: string | null;
  needs_manual_review?: string | boolean | null;
}

export interface LookupEvidence {
  ownership?: OwnershipEvidence;
  openalex_id?: string | null;
  countries?: string;
  institutions?: string;
  sri_lankan_institutions?: string;
  source_title?: string;
  source_authors?: (string | null)[];
  category?: LookupCategory;
}

export interface Contribution {
  contribution_id: string;
  profile_id: string;
  contribution_type: ContributionType;
  publication_key: string | null;
  proposed: Partial<Record<EditableField, string | number>> | NewPublicationProposal;
  base_snapshot: Partial<Record<EditableField, string | number | null>>;
  author_note: string;
  lookup_source: "manual" | "openalex" | "crossref";
  lookup_evidence: LookupEvidence;
  classifier: ClassifierResult;
  status: ContributionStatus;
  decision_reason: string;
  decided_by: string | null;
  decided_at: string | null;
  record_version: number;
  created_at: string;
  updated_at: string;
}

export interface DuplicateMatch {
  publication_key: string;
  title: string | null;
  publication_year: number | null;
  doi: string | null;
  is_public: boolean;
  hidden_reason: string | null;
}

export interface ReviewedContribution extends Contribution {
  profile: {
    display_name: string;
    slug: string;
    institution: string;
    orcid: string | null;
    email: string;
  };
  /** Publication edits only. */
  current?: Partial<Record<EditableField, string | number | null>>;
  publication_title?: string | null;
  stale_fields?: EditableField[];
  /** New publications only. */
  duplicates?: DuplicateMatch[];
  name_match?: NameMatch;
}

export interface WorkspaceLimits {
  max_pending_contributions: number;
  max_claims_per_request: number;
  editable_fields: Record<EditableField, string>;
  publication_types: string[];
}

export interface AuthorWorkspace {
  profile: AuthorProfile | null;
  claims: PublicationClaim[];
  contributions: Contribution[];
  limits: WorkspaceLimits;
  claims_added?: number;
}

export interface ApplicationReview extends AuthorProfile {
  claims: ReviewedClaim[];
  evidence: {
    email: { domain: string; kind: "academic" | "sri_lankan_organisation" | "free_webmail" | "other" | "unknown" };
    orcid_matches: number;
    orcid_held_by: string[];
  };
}

export interface ReviewPage<T> {
  records: T[];
  total?: number;
  page: number;
  page_size: number;
}

export interface DoiLookupResult {
  source: "openalex" | "crossref";
  doi: string;
  openalex_id: string | null;
  fields: Omit<NewPublicationProposal, "doi" | "your_author_name" | "publication_year" | "url" | "pdf_url"> & {
    publication_year: number | null;
    url: string;
    pdf_url: string;
  };
  ownership: OwnershipEvidence;
  duplicates: DuplicateMatch[];
  category?: LookupCategory;
}

export interface CategoryOption {
  field: string;
  domain: string | null;
  subfields: string[];
}

export interface InstitutionOption {
  label: string;
  country_code: string | null;
  sri_lankan: boolean;
  registered: boolean;
  publication_count: number;
}

export interface ClaimedNameProfile {
  slug: string;
  display_name: string;
  institution: string;
  claimed_count: number;
}

export interface AuthorNameOption {
  name: string;
  publication_count: number;
  year_min: number | null;
  year_max: number | null;
  profile: ClaimedNameProfile | null;
}

export interface AuthorLookupResult {
  names: AuthorNameOption[];
  profiles: { slug: string; display_name: string; institution: string; name_variants: string[] }[];
}

export interface AuthorQueueSummary {
  applications: number;
  claims: number;
  contributions: number;
}
