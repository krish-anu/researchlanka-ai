import type { Affiliation } from "@/types/authors";

/** Whether an affiliation covers a year; open ends count as covering it. */
export function coversYear(affiliation: Affiliation, year: number): boolean {
  return (
    (affiliation.start_year === null || affiliation.start_year <= year) &&
    (affiliation.end_year === null || year <= affiliation.end_year)
  );
}

/**
 * The institution an author was at in a given year, from their history.
 *
 * Used to pre-fill their own row on a publication they add, so a paper from
 * before a move is filed under the institution of the time. Falls back to the
 * current position, then to the institution on the profile.
 */
export function institutionForYear(
  affiliations: Affiliation[],
  year: number | null,
  fallback: string,
): string {
  if (year !== null) {
    const match = affiliations.find((affiliation) => coversYear(affiliation, year));
    if (match) return match.institution;
  }
  const current = affiliations.find((affiliation) => affiliation.end_year === null);
  return current?.institution ?? fallback;
}

/** "2016–2020", "2021–present", or "" when no years were given. */
export function periodLabel(affiliation: Pick<Affiliation, "start_year" | "end_year">): string {
  const { start_year: start, end_year: end } = affiliation;
  if (start === null && end === null) return "";
  if (end === null) return start === null ? "until now" : `${start}–present`;
  return start === null ? `until ${end}` : start === end ? String(start) : `${start}–${end}`;
}
