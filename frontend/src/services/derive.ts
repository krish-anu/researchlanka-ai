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

function publicationYear(publication: PublicationSummary): number | null {
  if (publication.publication_year !== null && publication.publication_year !== undefined) {
    return publication.publication_year;
  }
  if (!publication.publication_date) return null;
  const match = /^(\d{4})/.exec(publication.publication_date);
  return match ? Number(match[1]) : null;
}

export function yearHistogram(publications: PublicationSummary[]): YearBucket[] {
  const buckets = new Map<number, YearBucket>();
  const currentYear = new Date().getFullYear();

  for (const publication of publications) {
    const year = publicationYear(publication);
    if (year === null || year === undefined) continue;
    if (year < 2016 || year > currentYear) continue;
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

function normalizedText(value: string | null | undefined): string {
  return (value ?? "").trim().replace(/\s+/g, " ").toLowerCase();
}

function canonicalDoi(value: string | null | undefined): string | null {
  const doi = normalizedText(value)
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//, "")
    .replace(/^doi:/, "");
  if (!doi) return null;
  return doi.replace(/v\d+$/i, "");
}

function publicationIdentity(publication: PublicationSummary): string {
  const title = normalizedText(publication.title);
  const authors = publication.authors.slice(0, 4).map(normalizedText).join(";");
  const year = publication.publication_year ?? publicationYear(publication) ?? "";
  if (title && authors && year) {
    return ["work", title, authors, year].join("|");
  }
  const doi = canonicalDoi(publication.doi);
  if (doi) return `doi:${doi}`;
  return ["fallback", title, authors, year].join("|");
}

function sourceCount(publication: PublicationSummary): number {
  return publication.source_dataset.length;
}

function preferredPublication(
  current: PublicationSummary,
  candidate: PublicationSummary,
): PublicationSummary {
  if (sourceCount(candidate) !== sourceCount(current)) {
    return sourceCount(candidate) > sourceCount(current) ? candidate : current;
  }
  if (candidate.doi && !current.doi) return candidate;
  if (candidate.quality_flags.length !== current.quality_flags.length) {
    return candidate.quality_flags.length < current.quality_flags.length
      ? candidate
      : current;
  }
  return current;
}

export function publicationsForDisplay(
  publications: PublicationSummary[],
): PublicationSummary[] {
  const byIdentity = new Map<string, PublicationSummary>();

  for (const publication of publications) {
    if (!normalizedText(publication.title)) continue;
    const identity = publicationIdentity(publication);
    const existing = byIdentity.get(identity);
    byIdentity.set(
      identity,
      existing ? preferredPublication(existing, publication) : publication,
    );
  }

  return [...byIdentity.values()];
}
