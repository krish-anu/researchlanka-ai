"""
Author-disambiguation rules.

The pipeline is the standard three-stage one — block, score, cluster — with the
scoring stage weighted for what this corpus actually has:

  1. BLOCK      Group mentions by surname + first initial. Only within-block
                pairs are ever compared.
  2. COLLAPSE   Merge mentions whose parsed names are identical. This is exact,
                cheap, and removes most of the pairwise work.
  3. SCORE      Compare the remaining name variants inside each block using
                ORCID, coauthor and affiliation evidence.
  4. CLUSTER    Union-find over accepted merges, then label each cluster with
                the weakest evidence that built it.

Two decisions are worth stating outright, because they set the ceiling on what
this module can claim:

  * A shared *attributed* ORCID is decisive; a shared record-level ORCID set is
    not. Only ~10% of ORCID-bearing records permit attribution (see
    `evidence.align_orcids`), so ORCID resolves a minority of the corpus and
    everything else rests on weaker evidence.
  * Merges are conservative. An unmerged pair costs a split identity, which is
    visible and reviewable; a wrong merge fuses two researchers' publication
    records, which is not. Pairs in the uncertain band are left separate and
    sent to the review queue rather than guessed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from src.disambiguation.evidence import AuthorMention
from src.disambiguation.names import ParsedName, name_compatibility

__all__ = [
    "AuthorCluster",
    "DisambiguationResult",
    "PairDecision",
    "disambiguate_authors",
    "score_pair",
]


# Evidence weights. They sum to 1.0 so a score reads as a fraction of the
# available evidence, not an arbitrary point total.
WEIGHT_NAME = 0.45
WEIGHT_COAUTHOR = 0.30
WEIGHT_INSTITUTION = 0.15
WEIGHT_FIELD = 0.10

MERGE_THRESHOLD = 0.70
"""At or above this, two variants are the same person."""

HIGH_CONFIDENCE_THRESHOLD = 0.85
REVIEW_THRESHOLD = 0.45
"""Between this and MERGE_THRESHOLD: too close to call, send to review."""

MAX_VARIANTS_PER_BLOCK = 60
"""
Pairwise scoring is quadratic in block size. Blocks larger than this are almost
always a very common surname-initial combination ("perera|s"), where name
evidence is worthless anyway. Those blocks get ORCID and exact-name merging
only, and are flagged `oversized_block` for review rather than being scored
into a plausible-looking but unfounded clustering.
"""


class _DisjointSet:
    def __init__(self, items: Iterable[str]) -> None:
        self._parent = {item: item for item in items}

    def find(self, item: str) -> str:
        root = item
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[item] != root:  # path compression
            self._parent[item], item = root, self._parent[item]
        return root

    def union(self, left: str, right: str) -> None:
        left_root, right_root = self.find(left), self.find(right)
        if left_root != right_root:
            self._parent[right_root] = left_root

    def groups(self) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = defaultdict(list)
        for item in self._parent:
            grouped[self.find(item)].append(item)
        return dict(grouped)


@dataclass
class _NameVariant:
    """All mentions in one block that share an identical parsed name."""

    variant_id: str
    block: str
    name: ParsedName
    mentions: list[AuthorMention] = field(default_factory=list)

    @property
    def attributed_orcids(self) -> set[str]:
        return {mention.orcid for mention in self.mentions if mention.orcid}

    @property
    def record_orcids(self) -> set[str]:
        orcids: set[str] = set()
        for mention in self.mentions:
            orcids |= mention.record.orcids
        return orcids

    @property
    def institutions(self) -> set[str]:
        values: set[str] = set()
        for mention in self.mentions:
            values |= mention.record.institutions
        return values

    @property
    def coauthors(self) -> set[str]:
        values: set[str] = set()
        for mention in self.mentions:
            values |= mention.coauthor_keys
        return values - {self.block}

    @property
    def fields(self) -> set[str]:
        return {
            mention.record.primary_field
            for mention in self.mentions
            if mention.record.primary_field
        }

    @property
    def record_keys(self) -> set[str]:
        return {mention.record_key for mention in self.mentions}


@dataclass(frozen=True)
class PairDecision:
    """Why two name variants were or were not merged. Drives the review queue."""

    block: str
    left_id: str
    right_id: str
    left_name: str
    right_name: str
    score: float
    decision: str  # "merge" | "review" | "distinct" | "reject_orcid_conflict"
    basis: tuple[str, ...]

    @property
    def is_review(self) -> bool:
        return self.decision == "review"


def score_pair(left: _NameVariant, right: _NameVariant) -> PairDecision:
    """
    Score one within-block pair of name variants.

    Order of checks matters: identifier evidence overrides everything, in both
    directions. Two variants carrying *different* attributed ORCIDs are two
    different people no matter how similar their names or how many coauthors
    they share, and that rejection must not be outvoted by soft evidence.
    """
    left_orcids = left.attributed_orcids
    right_orcids = right.attributed_orcids
    basis: list[str] = []

    if left_orcids and right_orcids:
        if left_orcids & right_orcids:
            return PairDecision(
                block=left.block,
                left_id=left.variant_id,
                right_id=right.variant_id,
                left_name=left.name.raw,
                right_name=right.name.raw,
                score=1.0,
                decision="merge",
                basis=("orcid_match",),
            )
        return PairDecision(
            block=left.block,
            left_id=left.variant_id,
            right_id=right.variant_id,
            left_name=left.name.raw,
            right_name=right.name.raw,
            score=0.0,
            decision="reject_orcid_conflict",
            basis=("orcid_conflict",),
        )

    name_score = name_compatibility(left.name, right.name)
    if name_score == 0.0:
        return PairDecision(
            block=left.block,
            left_id=left.variant_id,
            right_id=right.variant_id,
            left_name=left.name.raw,
            right_name=right.name.raw,
            score=0.0,
            decision="distinct",
            basis=("name_conflict",),
        )

    score = WEIGHT_NAME * name_score
    basis.append(f"name:{name_score:.2f}")

    if left.coauthors & right.coauthors:
        score += WEIGHT_COAUTHOR
        basis.append("shared_coauthor")
    if left.institutions & right.institutions:
        score += WEIGHT_INSTITUTION
        basis.append("shared_institution")
    if left.fields & right.fields:
        score += WEIGHT_FIELD
        basis.append("shared_field")

    # A record-level ORCID set shared by both sides is corroboration, not proof:
    # it says the two mentions appear on records carrying the same identifier,
    # without saying the identifier belongs to *this* author.
    if not left_orcids and not right_orcids and (left.record_orcids & right.record_orcids):
        score += 0.05
        basis.append("shared_record_orcid_weak")

    score = min(score, 1.0)
    if score >= MERGE_THRESHOLD:
        decision = "merge"
    elif score >= REVIEW_THRESHOLD:
        decision = "review"
    else:
        decision = "distinct"

    return PairDecision(
        block=left.block,
        left_id=left.variant_id,
        right_id=right.variant_id,
        left_name=left.name.raw,
        right_name=right.name.raw,
        score=round(score, 3),
        decision=decision,
        basis=tuple(basis),
    )


@dataclass
class AuthorCluster:
    """One resolved author identity."""

    cluster_id: str
    canonical_name: str
    display_names: list[str]
    block: str
    mention_ids: list[str]
    record_keys: list[str]
    orcids: list[str]
    """Attributed ORCIDs only — a cluster with one of these is identifier-backed."""
    record_level_orcids: list[str]
    institutions: list[str]
    coauthor_blocks: list[str]
    confidence: str
    """`orcid_confirmed` | `high` | `medium` | `name_only`"""
    ambiguity_flags: list[str]
    publication_count: int
    year_min: int | None
    year_max: int | None

    @property
    def needs_review(self) -> bool:
        return bool(self.ambiguity_flags)


@dataclass
class DisambiguationResult:
    clusters: list[AuthorCluster]
    decisions: list[PairDecision]
    mention_to_cluster: dict[str, str]
    variant_to_cluster: dict[str, str]
    """Name-variant id -> cluster id. Lets the review queue tie a near-miss
    decision back to its cluster without re-deriving the variant id."""
    stats: dict[str, int]


def _canonical_name(variants: list[_NameVariant]) -> tuple[str, list[str]]:
    """
    Pick the display name for a cluster: the most complete name wins, then the
    most frequent. A cluster labelled "W. Perera" when it also contains "Wimal
    Perera" is needlessly less informative.
    """
    counted: dict[str, int] = defaultdict(int)
    for variant in variants:
        for mention in variant.mentions:
            counted[mention.name.raw] += 1

    def sort_key(item: tuple[str, int]) -> tuple[int, int, int]:
        raw, count = item
        words = len([token for token in raw.replace(".", " ").split() if len(token) > 1])
        return (-words, -count, len(raw))

    ordered = sorted(counted.items(), key=sort_key)
    return ordered[0][0], [name for name, _ in ordered]


def disambiguate_authors(mentions: list[AuthorMention]) -> DisambiguationResult:
    """Cluster author mentions into resolved identities."""
    # --- stage 1+2: block, then collapse identical parsed names ---------------
    #
    # Identical spellings collapse into one variant, with one exception: when a
    # spelling carries more than one attributed ORCID, it is more than one
    # person. Two researchers named "Wimal Perera" with distinct ORCIDs must not
    # be fused here, before the ORCID evidence is ever consulted. Those groups
    # split by ORCID, and any mentions of that spelling without an ORCID form a
    # further variant that cannot be assigned to either and goes to review.
    grouped: dict[tuple[str, str], list[AuthorMention]] = defaultdict(list)
    for mention in mentions:
        grouped[(mention.block, mention.name.normalized)].append(mention)

    variants: dict[str, _NameVariant] = {}
    blocks: dict[str, list[str]] = defaultdict(list)

    def add_variant(variant_id: str, block: str, name: ParsedName, members: list[AuthorMention]) -> None:
        variant = _NameVariant(variant_id=variant_id, block=block, name=name, mentions=members)
        variants[variant_id] = variant
        blocks[block].append(variant_id)

    for (block, normalized), members in grouped.items():
        distinct_orcids = {mention.orcid for mention in members if mention.orcid}
        base_id = f"{block}::{normalized}"
        if len(distinct_orcids) <= 1:
            add_variant(base_id, block, members[0].name, members)
            continue

        by_orcid: dict[str, list[AuthorMention]] = defaultdict(list)
        unassigned: list[AuthorMention] = []
        for mention in members:
            (by_orcid[mention.orcid] if mention.orcid else unassigned).append(mention)
        for orcid, orcid_members in by_orcid.items():
            add_variant(f"{base_id}::{orcid}", block, orcid_members[0].name, orcid_members)
        if unassigned:
            add_variant(f"{base_id}::_", block, unassigned[0].name, unassigned)

    disjoint = _DisjointSet(variants)
    decisions: list[PairDecision] = []
    oversized_blocks: set[str] = set()

    # --- ORCID pass: identifier evidence crosses block boundaries -------------
    # Two spellings of a name can land in different blocks ("Deepagoda, T.K.K.C."
    # vs "Thuduwe, Chamindu Deepagoda"). An attributed ORCID is strong enough to
    # merge across blocks, which pairwise scoring alone would never reach.
    by_orcid: dict[str, list[str]] = defaultdict(list)
    for variant_id, variant in variants.items():
        for orcid in variant.attributed_orcids:
            by_orcid[orcid].append(variant_id)
    for orcid, variant_ids in by_orcid.items():
        for other_id in variant_ids[1:]:
            disjoint.union(variant_ids[0], other_id)
            decisions.append(
                PairDecision(
                    block=variants[variant_ids[0]].block,
                    left_id=variant_ids[0],
                    right_id=other_id,
                    left_name=variants[variant_ids[0]].name.raw,
                    right_name=variants[other_id].name.raw,
                    score=1.0,
                    decision="merge",
                    basis=("orcid_match", f"orcid:{orcid}"),
                )
            )

    # --- stage 3: score remaining within-block pairs --------------------------
    for block, variant_ids in blocks.items():
        if len(variant_ids) > MAX_VARIANTS_PER_BLOCK:
            oversized_blocks.add(block)
            continue
        for index, left_id in enumerate(variant_ids):
            for right_id in variant_ids[index + 1 :]:
                decision = score_pair(variants[left_id], variants[right_id])
                decisions.append(decision)
                if decision.decision == "merge":
                    disjoint.union(left_id, right_id)

    # --- stage 4: assemble clusters ------------------------------------------
    #
    # Merge scores are indexed by cluster root in a single pass. Scanning every
    # merge decision once per cluster instead is O(clusters x merges), which on
    # the full corpus is 265k x 56k — it completes, but it dominates the entire
    # run.
    merge_scores_by_root: dict[str, list[float]] = defaultdict(list)
    for decision in decisions:
        if decision.decision != "merge":
            continue
        root = disjoint.find(decision.left_id)
        if disjoint.find(decision.right_id) == root:
            merge_scores_by_root[root].append(decision.score)

    review_by_variant: dict[str, list[PairDecision]] = defaultdict(list)
    conflict_by_variant: dict[str, list[PairDecision]] = defaultdict(list)
    for decision in decisions:
        if decision.decision == "review":
            review_by_variant[decision.left_id].append(decision)
            review_by_variant[decision.right_id].append(decision)
        elif decision.decision == "reject_orcid_conflict":
            conflict_by_variant[decision.left_id].append(decision)
            conflict_by_variant[decision.right_id].append(decision)

    clusters: list[AuthorCluster] = []
    mention_to_cluster: dict[str, str] = {}
    variant_to_cluster: dict[str, str] = {}

    for index, (root, member_ids) in enumerate(sorted(disjoint.groups().items())):
        members = [variants[member_id] for member_id in member_ids]
        cluster_id = f"A{index + 1:07d}"
        canonical, display_names = _canonical_name(members)

        attributed = sorted({orcid for member in members for orcid in member.attributed_orcids})
        record_orcids = sorted({orcid for member in members for orcid in member.record_orcids})
        record_keys = sorted({key for member in members for key in member.record_keys})
        mention_ids = [
            mention.mention_id for member in members for mention in member.mentions
        ]
        years = [
            mention.record.publication_year
            for member in members
            for mention in member.mentions
            if mention.record.publication_year is not None
        ]

        # Confidence is set by the *weakest* merge that built the cluster: a
        # chain is only as trustworthy as its loosest link.
        internal_scores = merge_scores_by_root.get(root, [])
        if attributed:
            confidence = "orcid_confirmed"
        elif not internal_scores:
            confidence = "name_only"
        elif min(internal_scores) >= HIGH_CONFIDENCE_THRESHOLD:
            confidence = "high"
        else:
            confidence = "medium"

        flags: list[str] = []
        if len(attributed) > 1:
            flags.append("multiple_orcids")
        if any(member.block in oversized_blocks for member in members):
            flags.append("oversized_block")
        if any(member_id in review_by_variant for member_id in member_ids):
            flags.append("near_threshold_pair")
        if any(member_id in conflict_by_variant for member_id in member_ids):
            flags.append("orcid_conflict_nearby")
        if confidence == "name_only" and len(record_keys) > 1:
            flags.append("name_only_multi_record")
        if all(member.name.is_surname_only for member in members):
            flags.append("surname_only")

        clusters.append(
            AuthorCluster(
                cluster_id=cluster_id,
                canonical_name=canonical,
                display_names=display_names,
                block=members[0].block,
                mention_ids=sorted(mention_ids),
                record_keys=record_keys,
                orcids=attributed,
                record_level_orcids=record_orcids,
                institutions=sorted({value for member in members for value in member.institutions}),
                coauthor_blocks=sorted({value for member in members for value in member.coauthors}),
                confidence=confidence,
                ambiguity_flags=flags,
                publication_count=len(record_keys),
                year_min=min(years) if years else None,
                year_max=max(years) if years else None,
            )
        )
        for mention_id in mention_ids:
            mention_to_cluster[mention_id] = cluster_id
        for member_id in member_ids:
            variant_to_cluster[member_id] = cluster_id

    stats = {
        "mentions": len(mentions),
        "name_variants": len(variants),
        "blocks": len(blocks),
        "oversized_blocks": len(oversized_blocks),
        "clusters": len(clusters),
        "clusters_orcid_confirmed": sum(1 for c in clusters if c.confidence == "orcid_confirmed"),
        "clusters_high": sum(1 for c in clusters if c.confidence == "high"),
        "clusters_medium": sum(1 for c in clusters if c.confidence == "medium"),
        "clusters_name_only": sum(1 for c in clusters if c.confidence == "name_only"),
        "clusters_flagged": sum(1 for c in clusters if c.needs_review),
        "pairs_scored": len(decisions),
        "pairs_merged": sum(1 for d in decisions if d.decision == "merge"),
        "pairs_review": sum(1 for d in decisions if d.decision == "review"),
        "pairs_orcid_conflict": sum(
            1 for d in decisions if d.decision == "reject_orcid_conflict"
        ),
    }

    return DisambiguationResult(
        clusters=clusters,
        decisions=decisions,
        mention_to_cluster=mention_to_cluster,
        variant_to_cluster=variant_to_cluster,
        stats=stats,
    )
