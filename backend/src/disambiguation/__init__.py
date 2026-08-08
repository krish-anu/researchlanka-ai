"""
Entity disambiguation: resolving author and institution mentions to identities.

Distinct from `src.deduplication`, which merges duplicate *records* of the same
publication. This package resolves the *entities* those records refer to.

    from src.disambiguation import disambiguate_authors, InstitutionResolver

The rules and their limits are documented in
`backend/docs/12_disambiguation_rules.md`.
"""

from src.disambiguation.authors import (
    AuthorCluster,
    DisambiguationResult,
    PairDecision,
    disambiguate_authors,
    score_pair,
)
from src.disambiguation.evidence import (
    AuthorMention,
    RecordEvidence,
    align_orcids,
    build_mentions,
    extract_record_evidence,
    normalize_orcid,
)
from src.disambiguation.institutions import (
    InstitutionResolution,
    InstitutionResolver,
    load_registry,
)
from src.disambiguation.names import (
    ParsedName,
    blocking_key,
    drop_intra_record_fragments,
    name_compatibility,
    parse_name,
    split_names,
)
from src.disambiguation.review import (
    AuthorReviewItem,
    InstitutionReviewItem,
    build_author_review_queue,
    build_institution_review_queue,
)

__all__ = [
    "AuthorCluster",
    "AuthorMention",
    "AuthorReviewItem",
    "DisambiguationResult",
    "InstitutionResolution",
    "InstitutionResolver",
    "InstitutionReviewItem",
    "PairDecision",
    "ParsedName",
    "RecordEvidence",
    "align_orcids",
    "blocking_key",
    "build_author_review_queue",
    "build_institution_review_queue",
    "build_mentions",
    "disambiguate_authors",
    "drop_intra_record_fragments",
    "extract_record_evidence",
    "load_registry",
    "name_compatibility",
    "normalize_orcid",
    "parse_name",
    "score_pair",
    "split_names",
]
