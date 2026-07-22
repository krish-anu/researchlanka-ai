"""Configurable duplicate detection without deleting source records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from research_analytics.cleaning import normalize_doi, normalize_title_key
from research_analytics.config import DeduplicationConfig


@dataclass
class DuplicateCandidate:
    left_index: int
    right_index: int
    match_type: str
    confidence: str
    merge_decision: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def find_duplicate_candidates(
    records: list[dict[str, Any]],
    config: DeduplicationConfig,
) -> list[DuplicateCandidate]:
    """Find duplicate candidates according to enabled rules."""

    if not config.enabled:
        return []

    candidates: list[DuplicateCandidate] = []
    seen_by_doi: dict[str, int] = {}
    seen_by_title_year: dict[tuple[str, str | None], int] = {}

    for index, record in enumerate(records):
        if config.doi_match_enabled:
            doi = normalize_doi(record.get("doi"))
            if doi:
                if doi in seen_by_doi:
                    candidates.append(
                        DuplicateCandidate(
                            left_index=seen_by_doi[doi],
                            right_index=index,
                            match_type="doi",
                            confidence="automatic",
                            merge_decision=(
                                "auto_merge" if config.doi_automatic_merge else "manual_review"
                            ),
                        )
                    )
                else:
                    seen_by_doi[doi] = index

        if config.exact_title_match_enabled:
            title_key = normalize_title_key(record.get("title"))
            if title_key:
                year = str(record.get("publication_year") or "") or None
                key = (
                    title_key,
                    year if config.exact_title_require_same_year else None,
                )
                if key in seen_by_title_year:
                    candidates.append(
                        DuplicateCandidate(
                            left_index=seen_by_title_year[key],
                            right_index=index,
                            match_type="exact_title",
                            confidence="review",
                            merge_decision="manual_review",
                        )
                    )
                else:
                    seen_by_title_year[key] = index

    return candidates
