/**
 * Author-name matching for the claim picker.
 *
 * A port of `name_match` in backend/src/api/services/author_profiles.py, used
 * only to preselect which listed author the applicant probably is. The
 * backend re-checks every claim and an administrator reviews it, so this is a
 * convenience, never a decision.
 */

export type NameMatch = "exact" | "initials" | "none";

const RANK: Record<NameMatch, number> = { none: 0, initials: 1, exact: 2 };

export function nameTokens(name: string): string[] {
  let text = name.normalize("NFKD").replace(/[̀-ͯ]/g, "");
  if (text.includes(",")) {
    const [surname, ...given] = text.split(",");
    text = `${given.join(" ")} ${surname}`;
  }
  return text.toLowerCase().match(/\p{L}+/gu) ?? [];
}

function matchTokens(left: string[], right: string[]): NameMatch {
  if (left.length === 0 || right.length === 0) return "none";
  if (left.join(" ") === right.join(" ")) return "exact";
  if (left[left.length - 1] !== right[right.length - 1]) return "none";
  const leftGiven = left.slice(0, -1).map((token) => token[0]);
  const rightGiven = right.slice(0, -1).map((token) => token[0]);
  if (leftGiven.length === 0 || rightGiven.length === 0) return "initials";
  const [shorter, longer] =
    leftGiven.length <= rightGiven.length ? [leftGiven, rightGiven] : [rightGiven, leftGiven];
  return shorter.every((initial) => longer.includes(initial)) ? "initials" : "none";
}

/** Both orders are tried, since Sri Lankan names often print surname first ("Perera A"). */
export function nameMatch(left: string, right: string): NameMatch {
  const leftTokens = nameTokens(left);
  const rightTokens = nameTokens(right);
  const candidates = [leftTokens];
  if (leftTokens.length > 1) candidates.push([...leftTokens.slice(1), leftTokens[0]]);
  return candidates
    .map((candidate) => matchTokens(candidate, rightTokens))
    .reduce<NameMatch>((best, match) => (RANK[match] > RANK[best] ? match : best), "none");
}

export function bestNameMatch(listed: string, names: string[]): NameMatch {
  return names.reduce<NameMatch>((best, name) => {
    const match = nameMatch(listed, name);
    return RANK[match] > RANK[best] ? match : best;
  }, "none");
}

/** The listed author most likely to be the applicant, or null when none plausibly is. */
export function likelyListedName(authors: string[], names: string[]): string | null {
  let chosen: string | null = null;
  let chosenRank = 0;
  for (const author of authors) {
    const rank = RANK[bestNameMatch(author, names)];
    if (rank > chosenRank) {
      chosen = author;
      chosenRank = rank;
    }
  }
  return chosen;
}
