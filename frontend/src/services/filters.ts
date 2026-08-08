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
  "field",
  "subfield",
  "topic",
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
  "citations_desc",
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
  return raw && VALID_SORTS.has(raw as SortOption)
    ? (raw as SortOption)
    : undefined;
}

export function extractPage(searchParams: SearchParams): number {
  const raw = firstValue(searchParams.page);
  const parsed = raw ? Number.parseInt(raw, 10) : 1;
  return Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
}

/** True when any real filter (beyond paging/sorting) is active. */
export function hasActiveFilters(filters: QueryParams): boolean {
  return Object.keys(filters).length > 0;
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
): string {
  const search = new URLSearchParams();
  for (const [key, raw] of Object.entries(searchParams)) {
    if (key === "page") continue;
    for (const item of toArray(raw)) search.append(key, item);
  }
  if (page > 1) search.set("page", String(page));
  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}
