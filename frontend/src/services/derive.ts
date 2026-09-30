/**
 * Client-side aggregations for views the API has no dedicated endpoint for.
 *
 * The API exposes national/institution analytics but no per-researcher trend,
 * so profile trends are derived from the returned publication page. Callers
 * must disclose that basis when the page does not cover the whole record set —
 * a truncated trend that looks authoritative is worse than a labelled one.
 */

import { formatNumber, formatRatioAsPercent } from "@/services/format";
import type { PublicationSummary, RankingEntry, TrendPoint } from "@/types/api";

export interface YearBucket {
  key: number;
  publication_count: number;
  citation_total: number;
}

function publicationYear(publication: PublicationSummary): number | null {
  if (
    publication.publication_year !== null &&
    publication.publication_year !== undefined
  ) {
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

/**
 * One-line trend takeaway for ChartPanel insight.
 * Prefers long-run % change when enough years exist; optionally notes OA share.
 */
export function trendInsight(
  points: Pick<TrendPoint, "key" | "publication_count">[],
  oaByYear?: Map<string, number>,
): string | undefined {
  if (!points.length) return undefined;
  const sorted = [...points].sort((a, b) => Number(a.key) - Number(b.key));
  const latest = sorted[sorted.length - 1];
  const prior = sorted[sorted.length - 2];
  const earliest = sorted[0];

  let line: string;
  if (prior && earliest && Number(latest.key) !== Number(earliest.key)) {
    const base = earliest.publication_count || 0;
    if (base > 0) {
      const delta = ((latest.publication_count - base) / base) * 100;
      const direction = delta >= 0 ? "rose" : "fell";
      line = `Output ${direction} ~${Math.abs(delta).toFixed(0)}% since ${earliest.key} (${formatNumber(latest.publication_count)} in ${latest.key}).`;
    } else {
      line = `${latest.key} recorded ${formatNumber(latest.publication_count)} AI publications, compared with ${formatNumber(prior.publication_count)} in ${prior.key}.`;
    }
  } else if (prior) {
    line = `${latest.key} recorded ${formatNumber(latest.publication_count)} AI publications, compared with ${formatNumber(prior.publication_count)} in ${prior.key}.`;
  } else {
    line = `${latest.key} recorded ${formatNumber(latest.publication_count)} AI publications.`;
  }

  if (oaByYear && latest) {
    const oa = oaByYear.get(String(latest.key));
    if (oa !== undefined && latest.publication_count > 0) {
      const share = oa / latest.publication_count;
      line += ` OA share is ${formatRatioAsPercent(share)}.`;
    }
  }

  return line;
}

/** Top-field lead line for distribution panels. */
export function fieldShareInsight(
  entries: { label: string; value: number }[],
): string | undefined {
  const top = entries[0];
  if (!top) return undefined;
  return `${top.label} leads this view with ${formatNumber(top.value)} publications.`;
}

/** Network size takeaway. */
export function networkInsight(
  nodeCount: number,
  edgeCount: number,
  scope: "institution" | "country" | "researcher",
): string {
  if (edgeCount <= 0) {
    return "No collaboration edges match the current density and filter settings.";
  }
  const entity =
    scope === "institution"
      ? "institutions"
      : scope === "researcher"
        ? "researchers"
        : "countries";
  return `This graph shows ${formatNumber(nodeCount)} ${entity} linked by ${formatNumber(edgeCount)} co-publication edges.`;
}

/** Ranking lead for institution lists from RankingEntry. */
export function rankingLeadInsight(entries: RankingEntry[]): string | undefined {
  const top = entries[0];
  if (!top) return undefined;
  return `${top.label} leads this view with ${formatNumber(top.publication_count)} publications.`;
}
