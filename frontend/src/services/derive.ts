/**
 * Client-side aggregations for views the API has no dedicated endpoint for.
 *
 * The API exposes national/institution analytics but no per-researcher trend,
 * so profile trends are derived from the returned publication page. Callers
 * must disclose that basis when the page does not cover the whole record set —
 * a truncated trend that looks authoritative is worse than a labelled one.
 */

import type { PublicationSummary } from "@/types/api";

export interface YearBucket {
  key: number;
  publication_count: number;
  citation_total: number;
}

export function yearHistogram(publications: PublicationSummary[]): YearBucket[] {
  const buckets = new Map<number, YearBucket>();

  for (const publication of publications) {
    const year = publication.publication_year;
    if (year === null || year === undefined) continue;
    const bucket = buckets.get(year) ?? {
      key: year,
      publication_count: 0,
      citation_total: 0,
    };
    bucket.publication_count += 1;
    bucket.citation_total += publication.citation_count ?? 0;
    buckets.set(year, bucket);
  }

  return [...buckets.values()].sort((a, b) => a.key - b.key);
}

/** Top topics across a publication set, for profile "publishes in" summaries. */
export function topValues(
  publications: PublicationSummary[],
  pick: (publication: PublicationSummary) => (string | null)[],
  limit = 8,
): { label: string; count: number }[] {
  const counts = new Map<string, number>();

  for (const publication of publications) {
    for (const value of pick(publication)) {
      if (!value) continue;
      counts.set(value, (counts.get(value) ?? 0) + 1);
    }
  }

  return [...counts.entries()]
    .map(([label, count]) => ({ label, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, limit);
}
