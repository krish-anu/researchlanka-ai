"""Configurable duplicate detection without deleting source records."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from difflib import SequenceMatcher
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
    score: float | None = None
    threshold: float | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _publication_year(record: dict[str, Any]) -> int | None:
    value = record.get("publication_year")
    if value is None:
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def _first_author_key(record: dict[str, Any]) -> str:
    value = record.get("author_names") or record.get("authors")
    if not value:
        return ""
    first_author = str(value).split(";")[0]
    return normalize_title_key(first_author)


def _years_compatible(
    left: int | None,
    right: int | None,
    *,
    maximum_difference: int,
) -> bool:
    if left is None or right is None:
        return False
    return abs(left - right) <= maximum_difference


def _authors_compatible(
    left: str,
    right: str,
    *,
    minimum_matching_authors: int,
) -> bool:
    if minimum_matching_authors <= 0:
        return True
    return bool(left and right and left == right)


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
    seen_title_records: list[tuple[int, str, int | None, str, str | None]] = []
    emitted_pairs: set[tuple[int, int, str]] = set()

    for index, record in enumerate(records):
        doi = normalize_doi(record.get("doi"))
        if config.doi_match_enabled:
            if doi:
                if doi in seen_by_doi:
                    pair_key = (seen_by_doi[doi], index, "doi")
                    emitted_pairs.add(pair_key)
                    candidates.append(
                        DuplicateCandidate(
                            left_index=seen_by_doi[doi],
                            right_index=index,
                            match_type="doi",
                            confidence="automatic",
                            merge_decision=(
                                "auto_merge" if config.doi_automatic_merge else "manual_review"
                            ),
                            score=100.0,
                            threshold=100.0,
                            reason="Same normalized DOI.",
                        )
                    )
                else:
                    seen_by_doi[doi] = index

        title_key = normalize_title_key(record.get("title"))
        year_value = _publication_year(record)
        author_key = _first_author_key(record)

        if config.exact_title_match_enabled:
            if title_key:
                key = (
                    title_key,
                    str(year_value) if config.exact_title_require_same_year and year_value else None,
                )
                if key in seen_by_title_year:
                    pair_key = (seen_by_title_year[key], index, "exact_title")
                    emitted_pairs.add(pair_key)
                    candidates.append(
                        DuplicateCandidate(
                            left_index=seen_by_title_year[key],
                            right_index=index,
                            match_type="exact_title",
                            confidence="review",
                            merge_decision="manual_review",
                            score=100.0,
                            threshold=100.0,
                            reason="Same normalized title and required year condition.",
                        )
                    )
                else:
                    seen_by_title_year[key] = index

        if config.fuzzy_title_match_enabled and title_key:
            for prior_index, prior_title_key, prior_year, prior_author_key, prior_doi in (
                seen_title_records
            ):
                if prior_title_key == title_key:
                    continue
                if not _years_compatible(
                    prior_year,
                    year_value,
                    maximum_difference=config.maximum_year_difference,
                ):
                    continue
                if not _authors_compatible(
                    prior_author_key,
                    author_key,
                    minimum_matching_authors=config.minimum_matching_authors,
                ):
                    continue
                if doi and prior_doi and doi == prior_doi:
                    continue

                score = round(SequenceMatcher(None, prior_title_key, title_key).ratio() * 100, 2)
                if score < config.fuzzy_title_threshold:
                    continue
                pair_key = (prior_index, index, "fuzzy_title")
                if pair_key in emitted_pairs:
                    continue
                emitted_pairs.add(pair_key)
                candidates.append(
                    DuplicateCandidate(
                        left_index=prior_index,
                        right_index=index,
                        match_type="fuzzy_title",
                        confidence="review",
                        merge_decision="manual_review",
                        score=score,
                        threshold=float(config.fuzzy_title_threshold),
                        reason=(
                            "Fuzzy normalized title score meets threshold with "
                            "compatible year and first-author evidence."
                        ),
                    )
                )

        if title_key:
            seen_title_records.append((index, title_key, year_value, author_key, doi))

    return candidates
