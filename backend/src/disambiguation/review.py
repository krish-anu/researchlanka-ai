"""
Review queues for ambiguous author and institution records.

Disambiguation cannot be finished by rules alone. What rules *can* do is refuse
to guess, and hand a human the cases where the evidence ran out — ranked so the
scarce review effort lands on the records that matter.

Both queues are ranked by impact rather than by score. A name-only cluster
holding 60 publications is worth an hour of somebody's time; the same
uncertainty on a single record is not. Every row states the evidence that was
found, what is missing, and the concrete action that would resolve it, so a
reviewer never has to re-derive the case from the raw data.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field

from src.disambiguation.authors import AuthorCluster, DisambiguationResult, PairDecision
from src.disambiguation.institutions import InstitutionResolution

__all__ = [
    "AuthorReviewItem",
    "InstitutionReviewItem",
    "build_author_review_queue",
    "build_institution_review_queue",
]


# What a reviewer should actually do, keyed by the flag that raised the case.
AUTHOR_ACTIONS = {
    "multiple_orcids": (
        "Cluster carries more than one ORCID. Split it, or confirm the person "
        "genuinely holds duplicate ORCID registrations."
    ),
    "oversized_block": (
        "Surname and initial are too common to score by name. Confirm against "
        "affiliation and coauthors, or accept that this block stays unresolved."
    ),
    "near_threshold_pair": (
        "A candidate merge scored just under the threshold. Confirm or reject "
        "the pair listed in `near_miss_pairs`."
    ),
    "orcid_conflict_nearby": (
        "A same-named variant carries a different ORCID. Check this cluster is "
        "not the unidentified half of that pair."
    ),
    "name_only_multi_record": (
        "Several records merged on name alone, with no ORCID, shared coauthor "
        "or shared affiliation. Verify before reporting as one researcher."
    ),
    "surname_only": (
        "Only a surname was recorded. Recover the given name from the source "
        "record if the publication count justifies it."
    ),
}


@dataclass
class AuthorReviewItem:
    cluster_id: str
    canonical_name: str
    confidence: str
    publication_count: int
    ambiguity_flags: list[str]
    actions: list[str]
    orcids: list[str]
    institutions: list[str]
    name_variants: list[str]
    near_miss_pairs: list[dict] = field(default_factory=list)
    sample_record_keys: list[str] = field(default_factory=list)
    priority: float = 0.0

    def as_row(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "canonical_name": self.canonical_name,
            "confidence": self.confidence,
            "publication_count": self.publication_count,
            "priority": round(self.priority, 3),
            "ambiguity_flags": "; ".join(self.ambiguity_flags),
            "review_actions": " | ".join(self.actions),
            "orcids": "; ".join(self.orcids),
            "name_variants": "; ".join(self.name_variants[:8]),
            "institutions": "; ".join(self.institutions[:5]),
            "near_miss_pairs": " | ".join(
                f"{pair['other_name']} (score {pair['score']}, {pair['basis']})"
                for pair in self.near_miss_pairs[:5]
            ),
            "sample_record_keys": "; ".join(self.sample_record_keys[:5]),
        }


@dataclass
class InstitutionReviewItem:
    raw_affiliation: str
    record_count: int
    method: str
    best_candidate: str | None
    score: float
    suggested_action: str
    priority: float = 0.0

    def as_row(self) -> dict:
        return {
            "raw_affiliation": self.raw_affiliation,
            "record_count": self.record_count,
            "resolution_method": self.method,
            "best_candidate": self.best_candidate or "",
            "match_score": round(self.score, 3),
            "priority": round(self.priority, 3),
            "suggested_action": self.suggested_action,
        }


def _cluster_priority(cluster: AuthorCluster) -> float:
    """
    Rank by how much wrongness the cluster could cause.

    Publication count sets the scale; the confidence tier sets the multiplier.
    An ORCID-confirmed cluster with a stray flag ranks below a name-only cluster
    of the same size, because the identifier already settles the identity.
    """
    weight = {
        "name_only": 1.0,
        "medium": 0.7,
        "high": 0.4,
        "orcid_confirmed": 0.15,
    }.get(cluster.confidence, 1.0)
    severity = 1.0 + 0.25 * len(cluster.ambiguity_flags)
    return cluster.publication_count * weight * severity


def build_author_review_queue(
    result: DisambiguationResult,
    *,
    min_publications: int = 1,
    limit: int | None = None,
) -> list[AuthorReviewItem]:
    """
    Build the ranked queue of author clusters a human should look at.

    Only flagged clusters are included. A cluster with no flags is not
    "reviewed and accepted" — it is a case where the rules found enough
    evidence, and re-checking every one of those by hand would be the same as
    having no rules at all.
    """
    reviews_by_variant: dict[str, list[PairDecision]] = defaultdict(list)
    for decision in result.decisions:
        if decision.is_review:
            reviews_by_variant[decision.left_id].append(decision)
            reviews_by_variant[decision.right_id].append(decision)

    variant_to_cluster = result.variant_to_cluster

    items: list[AuthorReviewItem] = []
    for cluster in result.clusters:
        if not cluster.needs_review or cluster.publication_count < min_publications:
            continue

        near_misses: list[dict] = []
        for variant_id, decisions in reviews_by_variant.items():
            if variant_to_cluster.get(variant_id) != cluster.cluster_id:
                continue
            for decision in decisions:
                other_name = (
                    decision.right_name
                    if variant_to_cluster.get(decision.left_id) == cluster.cluster_id
                    else decision.left_name
                )
                near_misses.append(
                    {
                        "other_name": other_name,
                        "score": decision.score,
                        "basis": ", ".join(decision.basis),
                    }
                )

        item = AuthorReviewItem(
            cluster_id=cluster.cluster_id,
            canonical_name=cluster.canonical_name,
            confidence=cluster.confidence,
            publication_count=cluster.publication_count,
            ambiguity_flags=cluster.ambiguity_flags,
            actions=[AUTHOR_ACTIONS[flag] for flag in cluster.ambiguity_flags if flag in AUTHOR_ACTIONS],
            orcids=cluster.orcids,
            institutions=cluster.institutions,
            name_variants=cluster.display_names,
            near_miss_pairs=sorted(near_misses, key=lambda pair: -pair["score"]),
            sample_record_keys=cluster.record_keys[:5],
            priority=_cluster_priority(cluster),
        )
        items.append(item)

    items.sort(key=lambda item: (-item.priority, item.canonical_name))
    return items[:limit] if limit else items


def build_institution_review_queue(
    resolutions: dict[str, InstitutionResolution],
    counts: Counter[str],
    *,
    limit: int | None = None,
) -> list[InstitutionReviewItem]:
    """
    Rank affiliation strings that the registry could not settle.

    Both unresolved strings and fuzzy matches are included: a fuzzy match is a
    guess the registry should be taught, by adding the alias, not a result to
    leave sitting at medium confidence forever.
    """
    items: list[InstitutionReviewItem] = []
    for raw, resolution in resolutions.items():
        if resolution.method not in {"unresolved", "registry_fuzzy"}:
            continue
        record_count = counts.get(raw, 0)

        if resolution.method == "registry_fuzzy":
            action = (
                f"Fuzzy match to '{resolution.preferred_name}' at {resolution.score}. "
                "Confirm and add this string as an alias in institutions.csv, or reject it."
            )
            # A fuzzy match is already usable, so it ranks below an outright miss.
            priority = record_count * 0.5
        elif resolution.score > 0:
            action = (
                f"Unresolved. Closest registry entry is '{resolution.matched_on}' at "
                f"{resolution.score}, below the {0.62} threshold. Add an alias, add a new "
                "institution, or mark out of scope."
            )
            priority = float(record_count)
        else:
            action = (
                "Unresolved with no registry overlap. Likely foreign, a government body, "
                "or a unit with no parent recorded. Add to institutions.csv or mark out of scope."
            )
            priority = float(record_count)

        items.append(
            InstitutionReviewItem(
                raw_affiliation=raw,
                record_count=record_count,
                method=resolution.method,
                best_candidate=resolution.preferred_name or resolution.matched_on,
                score=resolution.score,
                suggested_action=action,
                priority=priority,
            )
        )

    items.sort(key=lambda item: (-item.priority, item.raw_affiliation))
    return items[:limit] if limit else items
