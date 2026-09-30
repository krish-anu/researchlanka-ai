/**
 * URL helpers for entity routes.
 *
 * Two backend details drive the design here:
 *
 * 1. `publication_key` values can contain URLs such as
 *    `openalex:https://openalex.org/W1`. Encode the whole key as one segment:
 *    a literal `//` inside the page path is normalized to `/` by navigation.
 *    The catch-all route also accepts older links with literal slashes.
 *
 * 2. Researcher / institution / topic profiles are resolved by
 *    `repository._rows_for_multivalue`, which does `column ILIKE %value%`
 *    against the raw stored text. That means routes must carry the human
 *    **label** ("University of Colombo"), not the slugified `key`
 *    ("university-of-colombo") — the slug would never match. `RankingEntry`
 *    exposes both; always link with `label`.
 */

function encodePath(value: string): string {
  return value
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/");
}

/** Rejoin catch-all segments back into the original key. */
export function decodeKeySegments(segments: string[] | undefined): string {
  return (segments ?? []).map((segment) => decodeURIComponent(segment)).join("/");
}

/** Repair old OpenAlex links whose `https://` was collapsed by navigation. */
export function decodePublicationKeySegments(segments: string[] | undefined): string {
  return decodeKeySegments(segments).replace(/^openalex:(https?):\/([^/])/, "openalex:$1://$2");
}

export const publicationHref = (publicationKey: string) =>
  `/publications/${encodeURIComponent(publicationKey)}`;

export const researcherHref = (label: string) =>
  `/researchers/${encodePath(label)}`;

export const institutionHref = (label: string) =>
  `/institutions/${encodePath(label)}`;

export const topicHref = (label: string) => `/topics/${encodePath(label)}`;

/** Deep-link into publication search with one filter pre-applied. */
export function publicationSearchHref(
  filter: Record<string, string | number | undefined>,
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(filter)) {
    if (value === undefined || value === "") continue;
    search.append(key, String(value));
  }
  const qs = search.toString();
  return qs ? `/publications?${qs}` : "/publications";
}
