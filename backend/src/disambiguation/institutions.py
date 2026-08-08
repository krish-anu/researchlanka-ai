"""
Institution-disambiguation rules.

Affiliation strings are not institution names. They are addresses: unit, parent,
city, country, sometimes a postcode, in no fixed order and no fixed delimiter —
"Department of Civil Engineering, University of Moratuwa, Katubedda, Sri Lanka".
Resolving them means finding the *institution* inside the address.

The rules run in strict precedence order, most reliable first, and each records
which rule fired so a downstream reader can decide how much to trust it:

  1. ror              An explicit ROR identifier in the string. Unambiguous.
  2. registry_exact   The whole string is a known name or alias.
  3. registry_segment A comma-separated segment is a known name or alias. This
                      is what resolves the address case above.
  4. registry_fuzzy   Token overlap with a registry entry above threshold, with
                      the score kept for review.
  5. unresolved       Nothing matched. Reported, never silently dropped.

The registry itself is `research_analytics.institutions.NationalInstitutionRegistry`
loaded from `configurations/<country>/institutions.csv` — this module adds the
rule layers, it does not fork the registry.

A caution carried from the metadata review: `Department of Archaeology` (3,690
records) is a government department, not a university unit, and the registry is
the place to decide whether it is in scope. These rules will not invent that
judgement — an unlisted name stays unresolved.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from research_analytics.institutions import Institution, NationalInstitutionRegistry
from src.disambiguation.names import normalize_name_text

__all__ = [
    "InstitutionResolution",
    "InstitutionResolver",
    "extract_ror",
    "load_registry",
]


ROR_RE = re.compile(r"https?://ror\.org/([0-9a-z]+)", re.IGNORECASE)

FUZZY_THRESHOLD = 0.62
"""
Jaccard floor for accepting a fuzzy registry match.

Calibrated against the failure mode that matters: "University of Colombo" and
"University of Kelaniya" share "university" and score 0.33, while "Univ. of
Moratuwa" against "University of Moratuwa" scores 0.67. Below this floor the
shared tokens are almost always the generic ones.
"""

# Tokens that carry no institutional identity. Left in, they make every pair of
# universities look similar; the discriminating token is the place name.
STOPWORD_TOKENS = {
    "the", "of", "for", "and", "at", "in", "a",
    "university", "universities", "college", "institute", "institution",
    "univ", "uni",
    "school", "faculty", "department", "dept", "centre", "center", "unit",
    "division", "laboratory", "lab", "campus", "branch", "sri", "lanka",
    "srilanka", "ltd", "pvt", "limited", "inc",
}

# Address tail that is never part of the institution name.
POSTCODE_RE = re.compile(r"\b\d{4,6}\b")


def extract_ror(value: str) -> str | None:
    match = ROR_RE.search(str(value))
    return f"https://ror.org/{match.group(1).lower()}" if match else None


def _content_tokens(value: str) -> frozenset[str]:
    """
    Identity-bearing tokens only.

    Trailing punctuation is stripped per token, otherwise the abbreviation
    "Univ." never matches the stopword "univ" and abbreviated forms fail to
    resolve against their full names.
    """
    text = POSTCODE_RE.sub(" ", normalize_name_text(value))
    tokens = (token.strip(".,'-") for token in text.split())
    return frozenset(token for token in tokens if token and token not in STOPWORD_TOKENS)


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass(frozen=True)
class InstitutionResolution:
    """The outcome of resolving one affiliation string."""

    raw: str
    institution_id: str | None
    preferred_name: str | None
    ror_id: str | None
    method: str
    """`ror` | `registry_exact` | `registry_segment` | `registry_fuzzy` | `unresolved`"""
    confidence: str
    """`certain` | `high` | `medium` | `none`"""
    score: float
    matched_on: str | None
    """The substring that actually matched, so a reviewer can see the evidence."""

    @property
    def is_resolved(self) -> bool:
        return self.institution_id is not None


class InstitutionResolver:
    """Applies the rule cascade against a national institution registry."""

    def __init__(self, registry: NationalInstitutionRegistry) -> None:
        self.registry = registry
        # Keyed by the bare ROR id, so a registry entry stored as a full URL
        # still matches an id parsed out of an affiliation string.
        self._by_ror: dict[str, Institution] = {
            institution.ror_id.rsplit("/", 1)[-1].lower(): institution
            for institution in registry.institutions.values()
            if institution.ror_id
        }
        # Token profile per institution, built once from every name and alias.
        self._token_profiles: list[tuple[Institution, frozenset[str], str]] = []
        for institution in registry.institutions.values():
            for name in {institution.preferred_name, *institution.alternative_names}:
                tokens = _content_tokens(name)
                if tokens:
                    self._token_profiles.append((institution, tokens, name))

    def resolve(self, raw: str) -> InstitutionResolution:
        text = str(raw).strip()
        if not text:
            return InstitutionResolution(
                raw=text,
                institution_id=None,
                preferred_name=None,
                ror_id=None,
                method="unresolved",
                confidence="none",
                score=0.0,
                matched_on=None,
            )

        # 1. ROR identifier.
        ror = extract_ror(text)
        if ror:
            institution = self._by_ror.get(ror.rsplit("/", 1)[-1].lower())
            if institution is not None:
                return self._resolved(text, institution, "ror", "certain", 1.0, ror)

        # 2. Whole string is a known name or alias.
        institution = self._lookup(text)
        if institution is not None:
            return self._resolved(text, institution, "registry_exact", "high", 1.0, text)

        # 3. A comma-separated segment is. Longest segment first, so
        #    "University of Moratuwa" wins over a bare city name.
        segments = [segment.strip() for segment in text.split(",") if segment.strip()]
        for segment in sorted(segments, key=len, reverse=True):
            institution = self._lookup(segment)
            if institution is not None:
                return self._resolved(
                    text, institution, "registry_segment", "high", 1.0, segment
                )

        # 4. Fuzzy, against the whole string and each segment.
        best: tuple[float, Institution, str] | None = None
        for candidate in [text, *segments]:
            tokens = _content_tokens(candidate)
            if not tokens:
                continue
            for institution, profile_tokens, profile_name in self._token_profiles:
                score = _jaccard(tokens, profile_tokens)
                if best is None or score > best[0]:
                    best = (score, institution, profile_name)

        if best is not None and best[0] >= FUZZY_THRESHOLD:
            return self._resolved(
                text, best[1], "registry_fuzzy", "medium", round(best[0], 3), best[2]
            )

        return InstitutionResolution(
            raw=text,
            institution_id=None,
            preferred_name=None,
            ror_id=None,
            method="unresolved",
            confidence="none",
            score=round(best[0], 3) if best else 0.0,
            matched_on=best[2] if best else None,
        )

    def _lookup(self, value: str) -> Institution | None:
        institution_id = self.registry.alias_index.get(_registry_key(value))
        return self.registry.institutions.get(institution_id) if institution_id else None

    @staticmethod
    def _resolved(
        raw: str,
        institution: Institution,
        method: str,
        confidence: str,
        score: float,
        matched_on: str | None,
    ) -> InstitutionResolution:
        return InstitutionResolution(
            raw=raw,
            institution_id=institution.institution_id,
            preferred_name=institution.preferred_name,
            ror_id=institution.ror_id,
            method=method,
            confidence=confidence,
            score=score,
            matched_on=matched_on,
        )


def _registry_key(value: str) -> str:
    """Match `NationalInstitutionRegistry`'s own alias normalization."""
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower()).strip()


def load_registry(path: str | Path, *, country_code: str | None = None) -> NationalInstitutionRegistry:
    return NationalInstitutionRegistry.from_csv(path, country_code=country_code)
