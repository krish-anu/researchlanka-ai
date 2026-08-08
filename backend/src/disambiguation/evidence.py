"""
Evidence extraction for author disambiguation.

Three kinds of evidence are available in this corpus, in descending strength:

  ORCID        A persistent identifier. Decisive when it can be attributed to a
               specific author — see `align_orcids` for why that is usually
               impossible here.
  Affiliation  Two mentions of the same name at the same institution are more
               likely the same person. Weak on its own: large universities host
               many people who share a surname and initial.
  Coauthor     Two mentions sharing a coauthor are more likely the same person.
               The strongest *non-identifier* signal in bibliometrics, because
               research groups are small relative to the name space.

None of these is used as a standalone rule. `authors.py` combines them, and the
combination is what carries a confidence label.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.disambiguation.names import (
    ParsedName,
    blocking_key,
    drop_intra_record_fragments,
    normalize_name_text,
    parse_name,
    split_names,
)

__all__ = [
    "AuthorMention",
    "RecordEvidence",
    "align_orcids",
    "build_mentions",
    "extract_record_evidence",
    "normalize_orcid",
]


ORCID_RE = re.compile(r"\d{4}-\d{4}-\d{4}-\d{3}[\dX]", re.IGNORECASE)

# Sources that preserve author order alongside a per-author ORCID slot. Only
# these are eligible for positional ORCID attribution.
#
# `source_dataset` on a merged record is a semicolon-joined *list* of every
# source that contributed to it ("openalex; crossref"), not a single value, so
# this is an intersection test rather than a membership test.
ORDER_PRESERVING_SOURCES = {"openalex", "crossref"}


def normalize_orcid(value: str) -> str | None:
    """Reduce any ORCID spelling to its bare 16-character identifier."""
    match = ORCID_RE.search(str(value))
    return match.group(0).upper() if match else None


def _split_multi(value: object) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a", "[]"}:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


@dataclass(frozen=True)
class RecordEvidence:
    """Everything one publication record contributes to disambiguation."""

    record_key: str
    source_dataset: str | None
    publication_year: int | None
    names: tuple[ParsedName, ...]
    """Author mentions, after intra-record fragments are removed."""
    fragment_names: tuple[ParsedName, ...]
    orcids: frozenset[str]
    """Every ORCID on the record, whether or not it can be attributed."""
    orcid_by_position: tuple[str | None, ...]
    """Per-author ORCID where positional attribution is safe, else all None."""
    institutions: frozenset[str]
    countries: frozenset[str]
    primary_field: str | None

    @property
    def coauthor_keys(self) -> frozenset[str]:
        return frozenset(blocking_key(name) for name in self.names)


def align_orcids(
    names: list[ParsedName],
    orcids: list[str],
    *,
    source_dataset: str | None,
) -> list[str | None]:
    """
    Attribute ORCIDs to specific authors, or refuse to.

    This is the single most important correctness decision in the module. The
    merged `author_orcids` column is built by `unique_join`, which deduplicates
    and drops empties — so an ORCID at index *i* is not the ORCID of author
    *i*. Measured on the corpus, only 2,179 of 21,659 records with ORCIDs have
    equal author and ORCID counts; the other 90% cannot be positionally aligned
    at all.

    Positional attribution is therefore allowed only when every condition holds:

      * the record comes from an order-preserving source;
      * the counts match exactly;
      * there are no duplicate names (a repeated name makes position ambiguous).

    Otherwise this returns all-None and the ORCIDs stay *record-level* evidence:
    they can still say "these two mentions co-occur with the same ORCID set",
    which `authors.py` uses at reduced weight, but they cannot say "this author
    is that ORCID".
    """
    if not names or not orcids:
        return [None] * len(names)

    sources = {part.strip().casefold() for part in _split_multi(source_dataset)}
    if not sources & ORDER_PRESERVING_SOURCES:
        return [None] * len(names)

    # The count test is doing most of the work here. `author_orcids` is built by
    # `unique_join`, which drops empties and duplicates — so if the surviving
    # ORCID count still equals the author count, nothing was dropped and slot i
    # really is author i. A mismatch means the list was compacted and every
    # position after the first gap is wrong.
    if len(names) != len(orcids):
        return [None] * len(names)

    normalized_keys = [name.normalized for name in names]
    if len(set(normalized_keys)) != len(normalized_keys):
        return [None] * len(names)

    return [normalize_orcid(orcid) for orcid in orcids]


def extract_record_evidence(record: dict, *, record_key: str) -> RecordEvidence:
    """Pull the disambiguation-relevant fields out of one dataset row."""
    raw_names = split_names(record.get("authors"))
    parsed = [parsed for name in raw_names if (parsed := parse_name(name))]
    kept, fragments = drop_intra_record_fragments(parsed)

    orcids = [
        normalized
        for value in _split_multi(record.get("author_orcids"))
        if (normalized := normalize_orcid(value))
    ]

    year = record.get("publication_year")
    try:
        year_value = int(float(year)) if year is not None and str(year).strip() else None
    except (TypeError, ValueError):
        year_value = None

    # `sri_lankan_institutions` is far cleaner than `institutions` (3,445 vs
    # 26,211 distinct) but is the domestic subset only, so both feed the
    # affiliation signal.
    institutions = {
        normalize_name_text(value)
        for column in ("sri_lankan_institutions", "institutions")
        for value in _split_multi(record.get(column))
    } - {""}

    field_value = record.get("primary_field")
    primary_field = (
        normalize_name_text(field_value)
        if field_value is not None and str(field_value).strip()
        else None
    )

    return RecordEvidence(
        record_key=record_key,
        source_dataset=(record.get("source_dataset") or None),
        publication_year=year_value,
        names=tuple(kept),
        fragment_names=tuple(fragments),
        orcids=frozenset(orcids),
        orcid_by_position=tuple(
            align_orcids(kept, orcids, source_dataset=record.get("source_dataset"))
        ),
        institutions=frozenset(institutions),
        countries=frozenset(
            normalize_name_text(value) for value in _split_multi(record.get("countries"))
        )
        - {""},
        primary_field=primary_field or None,
    )


@dataclass(frozen=True)
class AuthorMention:
    """One author, as named on one record. The unit that gets clustered."""

    mention_id: str
    record_key: str
    position: int
    name: ParsedName
    orcid: str | None
    """Set only where positional attribution was safe."""
    record: RecordEvidence

    @property
    def block(self) -> str:
        return blocking_key(self.name)

    @property
    def coauthor_keys(self) -> frozenset[str]:
        """
        Other authors on the same record, as blocking keys.

        Blocking keys rather than names, so "Nimal de Silva" and "N. de Silva"
        count as the same collaborator. A coauthor sharing this mention's own
        key is excluded along with the mention itself — they would be
        indistinguishable from it and so carry no evidence.
        """
        own = blocking_key(self.name)
        return frozenset(blocking_key(other) for other in self.record.names) - {own}


def build_mentions(records: list[RecordEvidence]) -> list[AuthorMention]:
    """Flatten records into the author mentions that clustering operates on."""
    mentions: list[AuthorMention] = []
    for record in records:
        for position, name in enumerate(record.names):
            orcid = (
                record.orcid_by_position[position]
                if position < len(record.orcid_by_position)
                else None
            )
            mentions.append(
                AuthorMention(
                    mention_id=f"{record.record_key}#{position}",
                    record_key=record.record_key,
                    position=position,
                    name=name,
                    orcid=orcid,
                    record=record,
                )
            )
    return mentions
