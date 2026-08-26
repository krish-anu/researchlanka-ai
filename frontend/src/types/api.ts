/**
 * TypeScript contracts for the read-only ResearchLanka API (`/api/v1`).
 *
 * These mirror what `backend/src/api/{serializers,repository,aggregates}.py`
 * actually returns. Where `backend/docs/API_DESIGN.md` describes a different
 * shape than the implementation emits, the implementation wins and the
 * divergence is flagged with a NOTE comment so it is not silently designed
 * around.
 */

/* ---------------------------------------------------------------- envelopes */

export interface Pagination {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
}

export interface ResponseMeta {
  api_version: string;
  dataset_stage: string;
  snapshot_date: string | null;
  search?: {
    mode: "semantic" | "similarity" | string;
    algorithm?: string;
    min_score?: number | null;
  };
}

export interface ListResponse<T> {
  data: T[];
  pagination: Pagination;
  filters?: { applied: AppliedFilters };
  facets?: Facets;
  meta: ResponseMeta;
}

export interface DetailResponse<T> {
  data: T;
  meta: ResponseMeta;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}

/* ------------------------------------------------------------- publications */

export type QualityFlag =
  | "missing_doi"
  | "missing_abstract"
  | "missing_institutions"
  | "citation_count_divergence"
  | "reference_count_divergence"
  | "repository_only"
  | "no_doi_local_record"
  | "topic_model_source";

export interface PublicationSummary {
  publication_key: string;
  title: string | null;
  doi: string | null;
  publication_year: number | null;
  type: string | null;
  authors: string[];
  institutions: string[];
  journal: string | null;
  publisher: string | null;
  citation_count: number | null;
  reference_count: number | null;
  is_oa: boolean | null;
  oa_status: string | null;
  primary_field: string | null;
  primary_subfield: string | null;
  source_dataset: string[];
  quality_flags: QualityFlag[];
  semantic_score?: number;
  semantic_rank?: number;
  similarity_score?: number;
  similarity_rank?: number;
}

export interface PublicationDetail extends PublicationSummary {
  abstract: string | null;
  openalex_id: string | null;
  url: string | null;
  pdf_url: string | null;
  publication_date: string | null;
  author_orcids: string[];
  sri_lankan_authors: string | null;
  sri_lankan_institutions: string[];
  countries: string[];
  venue: {
    journal: string | null;
    publisher: string | null;
    issn: string[];
    issn_l: string | null;
    volume: string | null;
    issue: string | null;
    pages: {
      first: string | null;
      last: string | null;
      article_number: string | null;
    };
  };
  access: {
    is_oa: boolean | null;
    oa_status: string | null;
    license: string | null;
    license_url: string | null;
  };
  impact: {
    citation_count: number | null;
    reference_count: number | null;
    citation_count_difference_oa_minus_crossref: number | null;
    citation_count_divergence_flag: boolean | null;
    reference_count_difference_oa_minus_crossref: number | null;
    reference_count_divergence_flag: boolean | null;
  };
  classification: {
    concepts: string[];
    topics: string[];
    primary_topic: string | null;
    primary_field: string | null;
    primary_subfield: string | null;
    primary_domain: string | null;
  };
  funding: {
    funder_name: string[];
    funder_doi: string[];
    funder_identifier: string[];
    funder_award: string[];
  };
  provenance: {
    source_dataset: string[];
    source_institution_id: string | null;
    source_record_id: string | null;
    source_datestamp: string | null;
    raw_identifiers: unknown;
    raw_record_available: boolean;
  };
}

export interface PublicationReference {
  reference_id: string | number | null;
  publication_key: string;
  reference_index: number | null;
  reference_doi: string | null;
  reference_title: string | null;
  reference_author: string | null;
  reference_year: number | null;
  source_dataset: string | null;
  source_record_id: string | null;
  doi: string | null;
}

/* ----------------------------------------------------------------- filters */

export interface AppliedFilters {
  q?: string;
  year_min?: number;
  year_max?: number;
  type?: string[];
  institution?: string[];
  country?: string[];
  field?: string[];
  researcher?: string[];
  subfield?: string[];
  topic?: string[];
  journal?: string[];
  source_dataset?: string[];
  is_oa?: boolean;
  has_doi?: boolean;
  has_abstract?: boolean;
  quality_flag?: string[];
}

export type SortOption =
  | "relevance"
  | "year_desc"
  | "year_asc"
  | "citations_desc"
  | "title_asc";

export const SORT_OPTIONS: { value: SortOption; label: string }[] = [
  { value: "relevance", label: "Relevance" },
  { value: "year_desc", label: "Newest first" },
  { value: "year_asc", label: "Oldest first" },
  { value: "citations_desc", label: "Most cited" },
  { value: "title_asc", label: "Title A–Z" },
];

/** Facet name -> { facet value -> count }. */
export type Facets = Record<string, Record<string, number>>;

export interface Suggestion {
  value: string;
  type: "publication" | "journal" | string;
  key: string;
}

/* --------------------------------------------------------------- analytics */

export interface AnalyticsOverview {
  publication_count: number;
  citation_total: number;
  average_citations: number;
  /** 0..1 ratio, not a percentage. */
  open_access_share: number;
  doi_coverage: number;
  abstract_coverage: number;
  source_count: number;
  limitations: string[];
  // NOTE: API_DESIGN.md documents `institution_count` here, but
  // `repository.analytics_overview` does not emit it. Do not rely on it.
}

/**
 * NOTE: API_DESIGN.md shows `{ year, publication_count, citation_total }`, but
 * `repository.analytics_trends` emits a generic `key` (the grouped value —
 * a year when `group_by=year`, otherwise a type/field/institution label).
 */
export interface TrendPoint {
  key: string | number;
  publication_count: number;
  citation_total: number;
}

/** Shape returned by `analytics_rankings` — also used by
 *  `/researchers`, `/institutions`, `/topics` and `/fields`. */
export interface RankingEntry {
  /** Slugified label. Display-only: profile lookups match on `label`. */
  key: string;
  label: string;
  publication_count: number;
  citation_total: number;
}

/** `aggregate_profile()` output — shared by researcher and institution profiles. */
export interface ProfileAggregate {
  key: string;
  label: string;
  type: "researcher" | "institution";
  publication_count: number;
  citation_total: number;
  average_citations: number;
  year_min: number | null;
  year_max: number | null;
  disambiguation_level: string;
}

export interface CoauthorEntry {
  name: string;
  publication_count: number;
}

export interface CollaboratorEntry {
  institution: string;
  publication_count: number;
}

export interface NetworkNode {
  id: string;
  label: string;
  type: "institution" | "country" | "researcher" | string;
  publication_count: number;
  first_year?: number | null;
  last_year?: number | null;
  /**
   * Structural measures from `src/analytics/network.py`, computed over the
   * graph as returned — after `min_weight` and `limit` — so they describe the
   * picture on screen rather than the full corpus graph.
   */
  degree_centrality: number;
  /** Weighted degree: total co-publications, not distinct partners. */
  strength: number;
  /** Share of shortest paths through this node. High = bridging partner. */
  betweenness_centrality: number;
  closeness_centrality: number;
  /** Community id, 0-based and ordered by descending community size. */
  community: number;
}

/** Graph-level context needed to read the per-node measures honestly. */
export interface NetworkSummary {
  node_count: number;
  edge_count: number;
  density: number;
  component_count: number;
  largest_component_size: number;
  community_count: number;
  /** Newman-Girvan Q. Above ~0.3 the community split is meaningful. */
  modularity: number;
}

export interface NetworkEdge {
  source: string;
  target: string;
  source_label?: string;
  target_label?: string;
  weight: number;
  edge_type?: string;
  first_year?: number | null;
  last_year?: number | null;
}

export interface CollaborationNetwork {
  nodes: NetworkNode[];
  edges: NetworkEdge[];
  summary: NetworkSummary;
}

export interface DataQualitySummary {
  record_count: number;
  missing_doi_percentage: number;
  missing_abstract_percentage: number;
  missing_institutions_percentage: number;
  citation_divergence_count: number;
  reference_divergence_count: number;
  groups?: Record<
    string,
    {
      record_count: number;
      missing_doi_count: number;
      missing_abstract_count: number;
    }
  >;
}

/* -------------------------------------------------------- meta/limitations */

export interface DatasetMeta {
  api_version: string;
  dataset_stage: string;
  supported_filters: string[];
  supported_sorts: string[];
  publication_count?: number;
  min_publication_year?: number;
  max_publication_year?: number;
  max_loaded_at?: string | null;
  max_updated_at?: string | null;
}

export interface Limitations {
  limitations: string[];
  required_disclosures: string[];
  document: string;
}

export interface HealthStatus {
  status: "ok" | "unavailable";
  api_version: string;
}
