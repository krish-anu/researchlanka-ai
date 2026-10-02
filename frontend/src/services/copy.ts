/**
 * Denominator glossary — prefer these five phrases over inventing synonyms.
 *
 * 1. accepted AI collection — the corpus as a whole
 * 2. selected AI publications — records matching the current filters
 * 3. accepted AI records — countable publication rows in scope
 * 4. in this selection — qualifier when a filter window applies
 * 5. of selected AI publications — share / chart denominator under filters
 */
export const PHRASE = {
  acceptedAiCollection: "accepted AI collection",
  selectedAiPublications: "selected AI publications",
  acceptedAiRecords: "accepted AI records",
  inThisSelection: "in this selection",
  ofSelectedAiPublications: "of selected AI publications",
} as const;

/** Standard StatTile captions for analytics / directory KPI rows. */
export const CAPTION = {
  recordsInSelection: `Accepted AI records ${PHRASE.inThisSelection}`,
  institutionsInSelection: `With AI publications ${PHRASE.inThisSelection}`,
  shareOfSelected: `Share ${PHRASE.ofSelectedAiPublications}`,
  recordsInCollection: `Accepted AI records across the ${PHRASE.acceptedAiCollection}`,
} as const;

/**
 * Append a selection-scope clause to a chart description.
 * When filters apply: “… of selected AI publications.”
 * Otherwise: “… in the accepted AI collection.”
 */
export function withSelectionScope(
  lead: string,
  filtersApply: boolean,
): string {
  const base = lead.replace(/\.\s*$/, "");
  if (filtersApply) {
    return `${base} ${PHRASE.ofSelectedAiPublications}.`;
  }
  return `${base} in the ${PHRASE.acceptedAiCollection}.`;
}

/** True when any filter besides free-text `q` is active (years, facets, booleans). */
export function filtersNarrowSelection(
  filters: Record<string, unknown>,
): boolean {
  return Object.keys(filters).some((key) => key !== "q");
}
