/**
 * Translation between Next.js `searchParams` and API query parameters.
 *
 * Only filters the backend allowlists (`constants.LIST_FILTERS`) are forwarded;
 * anything else is dropped so a stray query string cannot produce a
 * `400 invalid_filter` from the API.
 */

import type { QueryParams } from "@/services/api";
import type { SortOption } from "@/types/api";

export type SearchParams = Record<string, string | string[] | undefined>;

/** Filters the API accepts on list and analytics endpoints. */
export const REPEATABLE_FILTERS = [
  "type",
  "institution",
  "country",
  "domain",
  "field",
  "researcher",
  "subfield",
  "topic",
  "nmf_topic",
  "nmf_topic_id",
  "journal",
  "source_dataset",
  "quality_flag",
] as const;

const SCALAR_FILTERS = ["q"] as const;
const NUMERIC_FILTERS = ["year_min", "year_max"] as const;
const BOOLEAN_FILTERS = ["is_oa", "has_doi", "has_abstract"] as const;

const VALID_SORTS = new Set<SortOption>([
  "relevance",
  "year_desc",
  "year_asc",
  "title_asc",
]);

function toArray(value: string | string[] | undefined): string[] {
  if (value === undefined) return [];
  return (Array.isArray(value) ? value : [value]).filter((item) => item !== "");
}

function firstValue(value: string | string[] | undefined): string | undefined {
  const values = toArray(value);
  return values.length > 0 ? values[0] : undefined;
}

/** Extract the API filter set from a page's `searchParams`. */
export function extractFilters(searchParams: SearchParams): QueryParams {
  const filters: QueryParams = {};

  for (const name of SCALAR_FILTERS) {
    const value = firstValue(searchParams[name]);
    if (value) filters[name] = value;
  }

  for (const name of NUMERIC_FILTERS) {
    const raw = firstValue(searchParams[name]);
    if (raw === undefined) continue;
    const parsed = Number.parseInt(raw, 10);
    if (Number.isFinite(parsed)) filters[name] = parsed;
  }

  // Never send an inverted range — swap so year_min ≤ year_max.
  if (
    typeof filters.year_min === "number" &&
    typeof filters.year_max === "number" &&
    filters.year_min > filters.year_max
  ) {
    const swapped = filters.year_min;
    filters.year_min = filters.year_max;
    filters.year_max = swapped;
  }

  for (const name of BOOLEAN_FILTERS) {
    const raw = firstValue(searchParams[name]);
    if (raw === "true" || raw === "false") filters[name] = raw;
  }

  for (const name of REPEATABLE_FILTERS) {
    const values = toArray(searchParams[name]);
    if (values.length > 0) filters[name] = values;
  }

  return filters;
}

export function extractSort(searchParams: SearchParams): SortOption | undefined {
  const raw = firstValue(searchParams.sort);
  if (!raw || !VALID_SORTS.has(raw as SortOption)) return undefined;
  if (raw === "relevance" && !firstValue(searchParams.q)) return undefined;
  return raw as SortOption;
}

export const PAGE_SIZE_OPTIONS = [10, 15, 20, 25, 50] as const;

/** Directory page length. Unknown values fall back so the API is not sent junk. */
export function extractPageSize(
  searchParams: SearchParams,
  fallback: (typeof PAGE_SIZE_OPTIONS)[number] = 15,
): number {
  const parsed = Number.parseInt(firstValue(searchParams.page_size) ?? "", 10);
  return (PAGE_SIZE_OPTIONS as readonly number[]).includes(parsed) ? parsed : fallback;
}

/** Publication-count floor for ranked directories. Not sent to other endpoints. */
export function extractMinCount(searchParams: SearchParams): number | undefined {
  const raw = firstValue(searchParams.min_count);
  if (!raw) return undefined;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

/** Publication-count ceiling. Used with the floor to match one landscape band. */
export function extractMaxCount(searchParams: SearchParams): number | undefined {
  const raw = firstValue(searchParams.max_count);
  if (!raw) return undefined;
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : undefined;
}

export function extractPage(
  searchParams: SearchParams,
  key = "page",
): number {
  const raw = firstValue(searchParams[key]);
  const parsed = raw ? Number.parseInt(raw, 10) : 1;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

/** True when any real filter (beyond paging/sorting) is active. */
export function hasActiveFilters(filters: QueryParams): boolean {
  return Object.keys(filters).length > 0;
}

/** True when a facet/range/boolean filter is active (excludes free-text `q`). */
export function hasFacetFilters(filters: QueryParams): boolean {
  return Object.keys(filters).some((key) => key !== "q");
}

/**
 * Count of active facet/range/boolean filters for “Filters (n)” badges.
 * Excludes free-text `q`, sort, and paging — matches ActiveFilters chips.
 */
export function countActiveFilters(searchParams: SearchParams): number {
  let count = 0;
  for (const name of REPEATABLE_FILTERS) {
    count += toArray(searchParams[name]).length;
  }
  for (const name of NUMERIC_FILTERS) {
    if (firstValue(searchParams[name])) count += 1;
  }
  for (const name of BOOLEAN_FILTERS) {
    const raw = firstValue(searchParams[name]);
    if (raw === "true" || raw === "false") count += 1;
  }
  return count;
}

/** Clamp year filters to dataset coverage and keep year_min ≤ year_max. */
export function clampYearFilters(
  filters: QueryParams,
  coverage: { start: number; end: number } | null | undefined,
): QueryParams {
  const next: QueryParams = { ...filters };
  let yearMin =
    typeof next.year_min === "number" ? next.year_min : undefined;
  let yearMax =
    typeof next.year_max === "number" ? next.year_max : undefined;

  if (coverage) {
    if (yearMin != null) {
      yearMin = Math.min(coverage.end, Math.max(coverage.start, yearMin));
    }
    if (yearMax != null) {
      yearMax = Math.min(coverage.end, Math.max(coverage.start, yearMax));
    }
  }

  if (yearMin != null && yearMax != null && yearMin > yearMax) {
    const swapped = yearMin;
    yearMin = yearMax;
    yearMax = swapped;
  }

  if (yearMin != null) next.year_min = yearMin;
  else delete next.year_min;
  if (yearMax != null) next.year_max = yearMax;
  else delete next.year_max;

  return next;
}

/**
 * Rebuild a query string with one value toggled on/off — used by facet chips
 * and filter pills. Always resets to page 1, since result counts change.
 */
export function toggleFilterHref(
  basePath: string,
  searchParams: SearchParams,
  name: string,
  value: string,
): string {
  const search = new URLSearchParams();

  for (const [key, raw] of Object.entries(searchParams)) {
    if (key === "page") continue;
    for (const item of toArray(raw)) {
      if (key === name && item === value) continue; // drop the toggled value
      search.append(key, item);
    }
  }

  const alreadyActive = toArray(searchParams[name]).includes(value);
  if (!alreadyActive) search.append(name, value);

  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

/** Same query string with a different page number. */
export function pageHref(
  basePath: string,
  searchParams: SearchParams,
  page: number,
  pageKey = "page",
): string {
  const search = new URLSearchParams();
  for (const [paramKey, raw] of Object.entries(searchParams)) {
    if (paramKey === pageKey) continue;
    for (const item of toArray(raw)) search.append(paramKey, item);
  }
  if (page > 1) search.set(pageKey, String(page));
  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

/** Same filters, a new page length, and page reset to the first page. */
export function pageSizeHref(
  basePath: string,
  searchParams: SearchParams,
  pageSize: number,
): string {
  const search = new URLSearchParams();
  for (const [paramKey, raw] of Object.entries(searchParams)) {
    if (paramKey === "page" || paramKey === "page_size") continue;
    for (const item of toArray(raw)) search.append(paramKey, item);
  }
  search.set("page_size", String(pageSize));
  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}
