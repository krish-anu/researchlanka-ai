"""Conservative national research ownership decisions.

The pipeline collects broad Sri Lanka-affiliated candidate records, then uses
these helpers to keep only evidence-backed Sri Lanka-led work in the verified
final dataset. Weak source, venue, repository, and first-author-only signals are
retained for review instead of being promoted to ownership.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable


DECISION_INCLUDE = "INCLUDE"
DECISION_REVIEW = "REVIEW"
DECISION_EXCLUDE = "EXCLUDE"

CONFIDENCE_HIGH = "HIGH"
CONFIDENCE_MEDIUM = "MEDIUM"
CONFIDENCE_LOW = "LOW"

OWNERSHIP_POLICY_VERSION = "1.0"
SRI_LANKA_COUNTRY_CODE = "LK"

OWNERSHIP_COLUMNS = [
    "ownership_decision",
    "ownership_class",
    "ownership_confidence",
    "ownership_reason",
    "ownership_evidence",
    "lead_country",
    "corresponding_author_countries",
    "has_sri_lankan_participant",
    "has_foreign_participant",
    "needs_manual_review",
    "ownership_policy_version",
]


@dataclass(frozen=True)
class OwnershipDecision:
    decision: str
    ownership_class: str
    confidence: str
    reason: str
    evidence: str
    lead_country: str = ""
    corresponding_author_countries: tuple[str, ...] = field(default_factory=tuple)
    has_sri_lankan_participant: bool = False
    has_foreign_participant: bool = False
    needs_manual_review: bool = True
    policy_version: str = OWNERSHIP_POLICY_VERSION

    @property
    def keep_in_strict_dataset(self) -> bool:
        return (
            self.decision == DECISION_INCLUDE
            and self.confidence in {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM}
            and not self.needs_manual_review
        )

    def as_dict(self) -> dict[str, Any]:
        corresponding = "; ".join(self.corresponding_author_countries)
        return {
            "ownership_decision": self.decision,
            "ownership_class": self.ownership_class,
            "ownership_classification": self.ownership_class,
            "ownership_confidence": self.confidence,
            "ownership_reason": self.reason,
            "ownership_evidence": self.evidence,
            "lead_country": self.lead_country,
            "country_owner": self.lead_country,
            "corresponding_author_countries": corresponding,
            "has_sri_lankan_participant": self.has_sri_lankan_participant,
            "has_foreign_participant": self.has_foreign_participant,
            "needs_manual_review": self.needs_manual_review,
            "ownership_policy_version": self.policy_version,
            "keep_in_strict_dataset": self.keep_in_strict_dataset,
            "keep_in_strict_sri_lanka_dataset": self.keep_in_strict_dataset,
            "keep_in_sri_lanka_owned_dataset": self.keep_in_strict_dataset,
        }


def country_text(countries: Iterable[str]) -> str:
    return "; ".join(sorted({country.upper() for country in countries if country}))


def openalex_publication_ownership(
    *,
    target_country: str,
    all_countries: set[str],
    first_author_countries: set[str],
    corresponding_author_countries: set[str],
) -> OwnershipDecision:
    target = target_country.upper()
    has_target = target in all_countries
    foreign = all_countries - {target}
    has_foreign = bool(foreign)
    corresponding = tuple(sorted(corresponding_author_countries))

    if not has_target:
        return OwnershipDecision(
            decision=DECISION_EXCLUDE,
            ownership_class="NO_LK_PUBLICATION_AFFILIATION",
            confidence=CONFIDENCE_HIGH if all_countries else CONFIDENCE_LOW,
            reason=f"No {target} publication-specific affiliation evidence is present.",
            evidence="openalex:authorship_affiliation_countries",
            lead_country=country_text(all_countries),
            corresponding_author_countries=corresponding,
            has_sri_lankan_participant=False,
            has_foreign_participant=has_foreign,
            needs_manual_review=False,
        )

    if corresponding_author_countries:
        lead_country = country_text(corresponding_author_countries)
        if corresponding_author_countries == {target}:
            return OwnershipDecision(
                decision=DECISION_INCLUDE,
                ownership_class=(
                    "SL_OWNED_INTERNATIONAL" if has_foreign else "SL_DOMESTIC"
                ),
                confidence=CONFIDENCE_MEDIUM,
                reason=(
                    f"Corresponding-author affiliation countries are exactly {target}; "
                    "foreign authors, if present, are collaborator evidence."
                ),
                evidence="openalex:corresponding_author_countries",
                lead_country=lead_country,
                corresponding_author_countries=corresponding,
                has_sri_lankan_participant=True,
                has_foreign_participant=has_foreign,
                needs_manual_review=False,
            )
        if target in corresponding_author_countries:
            return OwnershipDecision(
                decision=DECISION_REVIEW,
                ownership_class="CONFLICTING_CORRESPONDING_LEADERSHIP",
                confidence=CONFIDENCE_LOW,
                reason="Sri Lankan and foreign corresponding-author leadership signals conflict.",
                evidence="openalex:corresponding_author_countries",
                lead_country=lead_country,
                corresponding_author_countries=corresponding,
                has_sri_lankan_participant=True,
                has_foreign_participant=has_foreign,
                needs_manual_review=True,
            )
        return OwnershipDecision(
            decision=DECISION_EXCLUDE,
            ownership_class="FOREIGN_PROJECT_WITH_SL_PARTICIPATION",
            confidence=CONFIDENCE_MEDIUM,
            reason=(
                "Foreign corresponding-author affiliation indicates foreign leadership; "
                f"{target} appears as participant evidence only."
            ),
            evidence="openalex:corresponding_author_countries",
            lead_country=lead_country,
            corresponding_author_countries=corresponding,
            has_sri_lankan_participant=True,
            has_foreign_participant=has_foreign,
            needs_manual_review=False,
        )

    if first_author_countries:
        lead_country = country_text(first_author_countries)
        if target in first_author_countries:
            reason = (
                f"{target} first-author affiliation is only candidate evidence; "
                "no corresponding-author or project-lead evidence is available."
            )
            if first_author_countries - {target}:
                reason = (
                    f"First author has both {target} and foreign affiliations; "
                    "leadership is ambiguous without corresponding-author evidence."
                )
            return OwnershipDecision(
                decision=DECISION_REVIEW,
                ownership_class="FIRST_AUTHOR_ONLY_LK_EVIDENCE",
                confidence=CONFIDENCE_LOW,
                reason=reason,
                evidence="openalex:first_author_affiliation_countries",
                lead_country=lead_country,
                corresponding_author_countries=corresponding,
                has_sri_lankan_participant=True,
                has_foreign_participant=has_foreign,
                needs_manual_review=True,
            )

    return OwnershipDecision(
        decision=DECISION_REVIEW,
        ownership_class="MISSING_LEADERSHIP_EVIDENCE",
        confidence=CONFIDENCE_LOW,
        reason=f"{target} participation is present, but leadership cannot be determined.",
        evidence="openalex:participant_affiliation_without_leadership",
        lead_country=country_text(all_countries),
        corresponding_author_countries=corresponding,
        has_sri_lankan_participant=True,
        has_foreign_participant=has_foreign,
        needs_manual_review=True,
    )


def source_only_review(
    *,
    source: str,
    ownership_class: str,
    reason: str,
    has_sri_lankan_participant: bool = False,
) -> dict[str, Any]:
    decision = OwnershipDecision(
        decision=DECISION_REVIEW,
        ownership_class=ownership_class,
        confidence=CONFIDENCE_LOW,
        reason=reason,
        evidence=f"{source}:source_provenance_only",
        has_sri_lankan_participant=has_sri_lankan_participant,
        has_foreign_participant=False,
        needs_manual_review=True,
    )
    return decision.as_dict()


def resolved_keep(decision: Any, confidence: Any, needs_review: Any) -> bool:
    return (
        str(decision or "").upper() == DECISION_INCLUDE
        and str(confidence or "").upper() in {CONFIDENCE_HIGH, CONFIDENCE_MEDIUM}
        and str(needs_review).strip().casefold() not in {"true", "1", "yes", "y"}
    )
