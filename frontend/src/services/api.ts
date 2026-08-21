/**
 * Typed client for the read-only ResearchLanka API.
 *
 * Calls are made from React Server Components, so the browser never talks to
 * the Python service directly and no CORS negotiation is involved.
 *
 * The backend requires PostgreSQL with a loaded `final_publications` table. A
 * cold or unreachable API is therefore a normal state for a developer running
 * only the frontend, not an exceptional one — so every call returns an
 * `ApiResult` and pages render an explanatory panel instead of crashing.
 */

import type {
  AnalyticsOverview,
  ApiErrorBody,
  CoauthorEntry,
  CollaborationNetwork,
  CollaboratorEntry,
  DataQualitySummary,
  DatasetMeta,
  DetailResponse,
  Facets,
  HealthStatus,
  Limitations,
  ListResponse,
  ProfileAggregate,
  PublicationDetail,
  PublicationReference,
  PublicationSummary,
  RankingEntry,
  ResponseMeta,
  Suggestion,
  TrendPoint,
} from "@/types/api";

export const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8080/api/v1";

/** Requests are capped so one slow analytics scan cannot hang a page render. */
const REQUEST_TIMEOUT_MS = 20_000;

export interface ApiFailure {
  code: string;
  message: string;
  status: number | null;
  details?: Record<string, unknown>;
}

export type ApiResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: ApiFailure };

export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | (string | number)[];

export type QueryParams = Record<string, QueryValue>;

/** Repeatable filters are emitted as repeated keys, matching `parse_qs`. */
export function buildQuery(params: QueryParams = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === null || value === undefined || value === "") continue;
    if (Array.isArray(value)) {
      for (const item of value) {
        if (item === null || item === undefined || item === "") continue;
        search.append(key, String(item));
      }
    } else {
      search.append(key, String(value));
    }
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

interface RequestOptions {
  /** Seconds of ISR caching. `0` disables caching for user-driven searches. */
  revalidate?: number;
}

async function request<T>(
  path: string,
  params: QueryParams = {},
  options: RequestOptions = {},
): Promise<ApiResult<T>> {
  const url = `${API_BASE_URL}${path}${buildQuery(params)}`;
  const revalidate = options.revalidate ?? 300;

  try {
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      ...(revalidate === 0
        ? { cache: "no-store" as const }
        : { next: { revalidate } }),
    });

    if (!response.ok) {
      let body: ApiErrorBody | null = null;
      try {
        body = (await response.json()) as ApiErrorBody;
      } catch {
        // Non-JSON error body (proxy error page, etc.) — fall through.
      }
      return {
        ok: false,
        error: {
          code: body?.error?.code ?? `http_${response.status}`,
          message:
            body?.error?.message ??
            `Request failed with HTTP ${response.status}.`,
          status: response.status,
          details: body?.error?.details,
        },
      };
    }

    return { ok: true, value: (await response.json()) as T };
  } catch (cause) {
    const isTimeout =
      cause instanceof DOMException && cause.name === "TimeoutError";
    return {
      ok: false,
      error: {
        code: isTimeout ? "timeout" : "unreachable",
        message: isTimeout
          ? `The API did not respond within ${REQUEST_TIMEOUT_MS / 1000}s.`
          : `Could not reach the API at ${API_BASE_URL}.`,
        status: null,
      },
    };
  }
}

/** Narrow an `ApiResult` to its value, or fall back. */
export function valueOr<T>(result: ApiResult<T>, fallback: T): T {
  return result.ok ? result.value : fallback;
}

/** `true` when the failure means "no such record" rather than "API is broken". */
export function isNotFound<T>(result: ApiResult<T>): boolean {
  return !result.ok && result.error.status === 404;
}

export const EMPTY_META: ResponseMeta = {
  api_version: "v1",
  dataset_stage: "final_publications",
  snapshot_date: null,
};

/* --------------------------------------------------------- health & schema */

export const getHealth = () =>
  request<DetailResponse<HealthStatus>>("/health", {}, { revalidate: 0 });

export const getDatasetMeta = () =>
  request<DetailResponse<DatasetMeta>>("/meta", {}, { revalidate: 0 });

export const getLimitations = () =>
  request<DetailResponse<Limitations>>("/limitations", {}, { revalidate: 3600 });

/* ------------------------------------------------------------ publications */

export const listPublications = (params: QueryParams) =>
  request<ListResponse<PublicationSummary>>("/publications", params, {
    revalidate: 0,
  });

export const searchSimilarPublications = (params: QueryParams) =>
  request<ListResponse<PublicationSummary>>("/search/similarity", params, {
    revalidate: 0,
  });

export const getPublication = (publicationKey: string) =>
  request<DetailResponse<PublicationDetail>>(
    `/publications/${encodeURIComponent(publicationKey)}`,
  );

export const getSimilarPublications = (
  publicationKey: string,
  params: QueryParams = {},
) =>
  request<ListResponse<PublicationSummary>>(
    `/publications/${encodeURIComponent(publicationKey)}/similar`,
    params,
  );

export const getPublicationReferences = (
  publicationKey: string,
  params: QueryParams = {},
) =>
  request<ListResponse<PublicationReference>>(
    `/publications/${encodeURIComponent(publicationKey)}/references`,
    params,
  );

export const getSuggestions = (q: string, limit = 10) =>
  request<DetailResponse<Suggestion[]>>(
    "/search/suggest",
    { q, limit },
    { revalidate: 0 },
  );

export const getFacets = (params: QueryParams = {}) =>
  request<{ data: Facets; meta: ResponseMeta }>("/search/facets", params, {
    revalidate: 0,
  });

/* -------------------------------------------------------------- researchers */

export const listResearchers = (params: QueryParams = {}) =>
  request<ListResponse<RankingEntry>>("/researchers", params, {
    revalidate: 0,
  });

export const getResearcher = (researcherKey: string) =>
  request<DetailResponse<ProfileAggregate>>(
    `/researchers/${encodeURIComponent(researcherKey)}`,
  );

export const getResearcherPublications = (
  researcherKey: string,
  params: QueryParams = {},
) =>
  request<ListResponse<PublicationSummary>>(
    `/researchers/${encodeURIComponent(researcherKey)}/publications`,
    params,
  );

export const getResearcherCoauthors = (
  researcherKey: string,
  params: QueryParams = {},
) =>
  request<DetailResponse<CoauthorEntry[]>>(
    `/researchers/${encodeURIComponent(researcherKey)}/coauthors`,
    params,
  );

/* ------------------------------------------------------------- institutions */

export const listInstitutions = (params: QueryParams = {}) =>
  request<ListResponse<RankingEntry>>("/institutions", params);

export const getInstitution = (institutionKey: string) =>
  request<DetailResponse<ProfileAggregate>>(
    `/institutions/${encodeURIComponent(institutionKey)}`,
  );

export const getInstitutionPublications = (
  institutionKey: string,
  params: QueryParams = {},
) =>
  request<ListResponse<PublicationSummary>>(
    `/institutions/${encodeURIComponent(institutionKey)}/publications`,
    params,
  );

export const getInstitutionCollaborators = (
  institutionKey: string,
  params: QueryParams = {},
) =>
  request<DetailResponse<CollaboratorEntry[]>>(
    `/institutions/${encodeURIComponent(institutionKey)}/collaborators`,
    params,
  );

/** Requires 2–3 institution labels; the API rejects any other count. */
export const compareInstitutions = (institutions: string[]) =>
  request<DetailResponse<ProfileAggregate[]>>("/institutions/compare", {
    institution: institutions,
  });

/* ---------------------------------------------------------- topics & fields */

export const listTopics = (params: QueryParams = {}) =>
  request<ListResponse<RankingEntry>>("/topics", params);

export const getTopicPublications = (
  topicKey: string,
  params: QueryParams = {},
) =>
  request<ListResponse<PublicationSummary>>(
    `/topics/${encodeURIComponent(topicKey)}/publications`,
    params,
  );

export const listFields = (
  params: QueryParams & { level?: "domain" | "field" | "subfield" | "topic" } = {},
) => request<ListResponse<RankingEntry>>("/fields", params);

/* ---------------------------------------------------------------- analytics */

export const getAnalyticsOverview = (params: QueryParams = {}) =>
  request<DetailResponse<AnalyticsOverview>>("/analytics/overview", params, {
    revalidate: 0,
  });

export const getAnalyticsTrends = (
  params: QueryParams & {
    group_by?: "year" | "type" | "field" | "institution";
    metric?: "publications" | "citations";
  } = {},
) =>
  request<DetailResponse<TrendPoint[]>>("/analytics/trends", params, {
    revalidate: 0,
  });

export const getAnalyticsInstitutions = (params: QueryParams = {}) =>
  request<ListResponse<RankingEntry>>("/analytics/institutions", params, {
    revalidate: 0,
  });

export const getAnalyticsFields = (params: QueryParams = {}) =>
  request<ListResponse<RankingEntry>>("/analytics/fields", params, {
    revalidate: 0,
  });

export const getCollaborationNetwork = (
  params: QueryParams & {
    scope?: "institution" | "country" | "researcher";
    min_weight?: number;
    limit?: number;
  } = {},
) =>
  request<DetailResponse<CollaborationNetwork>>(
    "/analytics/collaboration-network",
    params,
    { revalidate: 0 },
  );

export const getDataQuality = (
  params: QueryParams & {
    group_by?: "source_dataset" | "type" | "institution" | "year";
  } = {},
) =>
  request<DetailResponse<DataQualitySummary>>("/analytics/data-quality", params, {
    revalidate: 0,
  });

/* ------------------------------------------------------------------ exports */

/** Absolute URL for a CSV/JSONL download; the browser hits the API directly. */
export function exportUrl(
  kind: "publications.csv" | "publications.jsonl",
  params: QueryParams = {},
): string {
  return `${API_BASE_URL}/exports/${kind}${buildQuery(params)}`;
}

export function analyticsExportUrl(
  name: "overview" | "trends" | "institutions" | "fields" | "data-quality",
  params: QueryParams = {},
): string {
  return `${API_BASE_URL}/exports/analytics/${name}.csv${buildQuery(params)}`;
}
