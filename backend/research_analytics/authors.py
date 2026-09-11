"""Author name parsing, ORCID validation and evidence-based author disambiguation.

Author identity has to be rebuilt from record-level metadata: ``authors`` is a
semicolon-joined name list and ``author_orcids``, ``author_affiliations`` and
the normalized institution fields describe the *record*, not an individual
author position. Disambiguation therefore works on **name variants** -- one
entry per distinct spelling of a name -- and merges variants into author
clusters only on evidence a reviewer can be pointed at:

1. ``orcid``       -- two variants carrying the same ORCID are the same person.
2. ``affiliation`` -- compatible names sharing an institution.
3. ``coauthor``    -- compatible names sharing a coauthor.
4. ``name``        -- an initialled name joins the only spelled-out name in its
   surname block that it fits, and only when no affiliation contradicts it.

Two rules constrain everything above:

* Nothing merges on a similarity score. Every merge names the evidence that
  produced it, so any cluster can be explained and any rule can be re-run.
* Differing ORCIDs are a hard block. No automatic rule may merge two variants
  whose ORCID sets are non-empty and disjoint; only an explicit human decision
  can, and the resulting cluster is flagged for review.

What is deliberately *not* attempted: two different people who publish under
exactly the same spelling of the same name are one variant and cannot be split
by these rules. They are surfaced for review, never silently separated.
"""

from __future__ import annotations

import csv
import hashlib
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from research_analytics.institutions import normalize_lookup_key


__all__ = [
    "AuthorCluster",
    "AuthorDecision",
    "AuthorDisambiguationResult",
    "AuthorMention",
    "AuthorName",
    "AuthorReviewPair",
    "AuthorVariant",
    "AuthorVariantIndex",
    "author_blocking_key",
    "author_mentions",
    "author_variant_key",
    "disambiguate_authors",
    "load_author_decisions",
    "name_is_more_specific",
    "names_compatible",
    "normalize_orcid",
    "parse_author_name",
    "record_institution_keys",
    "split_author_field",
]


# --- matching vocabulary ----------------------------------------------------

MATCH_METHOD_REVIEWED = "reviewed"
MATCH_METHOD_ORCID = "orcid"
MATCH_METHOD_AFFILIATION = "affiliation"
MATCH_METHOD_COAUTHOR = "coauthor"
MATCH_METHOD_NAME = "name"
MATCH_METHOD_SINGLETON = "singleton"

# Ordered weakest to strongest. A cluster reports the strongest evidence that
# built it, so "orcid" never gets hidden behind a later name-only merge, and a
# reviewed verdict outranks everything -- it is the one judgement made by a
# person who could look outside this corpus.
MATCH_METHOD_PRECEDENCE = (
    MATCH_METHOD_SINGLETON,
    MATCH_METHOD_NAME,
    MATCH_METHOD_COAUTHOR,
    MATCH_METHOD_AFFILIATION,
    MATCH_METHOD_ORCID,
    MATCH_METHOD_REVIEWED,
)

CONFIDENCE_BY_METHOD = {
    MATCH_METHOD_REVIEWED: "high",
    MATCH_METHOD_ORCID: "high",
    MATCH_METHOD_AFFILIATION: "medium",
    MATCH_METHOD_COAUTHOR: "medium",
    MATCH_METHOD_NAME: "low",
    MATCH_METHOD_SINGLETON: "low",
}

REVIEW_COMPATIBLE_NAMES_NO_EVIDENCE = "compatible_names_no_evidence"
REVIEW_EVIDENCE_SEVERAL_PEOPLE = "evidence_points_to_more_than_one_person"
REVIEW_INITIALS_ONLY = "initials_only_name"
REVIEW_MERGED_ON_NAME_ONLY = "merged_on_name_only"
REVIEW_MANUAL_ORCID_OVERRIDE = "manual_merge_overrides_orcid_conflict"
REVIEW_OVERSIZED_BLOCK = "surname_block_too_large_for_pairwise_review"

DECISION_SAME = "same_author"
DECISION_DIFFERENT = "different_author"
DECISION_VALUES = frozenset({DECISION_SAME, DECISION_DIFFERENT})

# Guards on the two quadratic stages. Sri Lankan surname blocks are long-tailed:
# a handful of surnames carry a large share of the corpus, and comparing every
# spelling against every other inside those blocks is what would make a full-run
# expensive. Blocks above the limit still cluster on ORCID (which is global);
# they simply skip pairwise evidence matching and are reported for review.
DEFAULT_MAX_BLOCK_VARIANTS = 2_000
DEFAULT_MAX_REVIEW_ROOTS_PER_BLOCK = 25

# Sample record identifiers kept per variant, to give a reviewer something to
# open without holding the whole corpus in memory.
SAMPLE_RECORDS_PER_VARIANT = 5


# --- name parsing -----------------------------------------------------------

# Titles carried into the name string by repository metadata.
HONORIFIC_RE = re.compile(
    r"^(?:prof(?:essor)?|dr|doctor|mr|mrs|ms|miss|rev|sir|eng|ir|hon)\b\.?\s+",
    re.IGNORECASE,
)

# Trailing tokens that qualify a name rather than form part of it. Degrees are
# common in repository metadata ("Perera, K., MBBS") and generational suffixes
# in Crossref.
SUFFIX_TOKENS = frozenset(
    """
    jr jnr sr snr ii iii iv v phd ph d dphil mphil msc bsc ma mba md mbbs bds
    dvm frcp frcs facs fracp fcp mrcp dsc dr eng esq emeritus retd
    """.split()
)

# Particles that belong to the surname they precede.
SURNAME_PARTICLES = frozenset(
    """
    de del della di da das dos du van von der den ter ten le la el al bin ibn
    bint abu mac mc st saint
    """.split()
)

INLINE_ORCID_RE = re.compile(
    r"\(?\s*(?:https?://(?:www\.)?orcid\.org/)?(\d{4}-\d{4}-\d{4}-\d{3}[\dXx])\s*\)?"
)

ORCID_RE = re.compile(r"(\d{4})-?(\d{4})-?(\d{4})-?(\d{3})([\dXx])")

WHITESPACE_RE = re.compile(r"\s+")

# "R.M.K.", "R.M.K" or "R.M" -- a dotted run of initials rather than a given
# name. The trailing dot is optional because cleaning strips it from the end of
# the name string.
DOTTED_INITIALS_RE = re.compile(r"^[A-Za-z]\.(?:\s*[A-Za-z]\.?)+$")


@dataclass(frozen=True)
class AuthorName:
    """A parsed name, reduced to the parts that matching is allowed to use."""

    display: str
    surname: str
    given: tuple[str, ...]
    surname_display: str

    @property
    def initials(self) -> tuple[str, ...]:
        return tuple(token[0] for token in self.given if token)

    @property
    def is_initials_only(self) -> bool:
        """True when nothing in the name is spelled out beyond an initial."""

        return not any(len(token) > 1 for token in self.given)

    @property
    def variant_key(self) -> str:
        return f"{self.surname}|{'.'.join(self.given)}"

    @property
    def blocking_key(self) -> str:
        initials = self.initials
        return f"{self.surname}|{initials[0] if initials else ''}"


def strip_accents(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _normalize_token(value: str) -> str:
    """Reduce a name token to comparable ASCII letters and digits."""

    token = strip_accents(value).replace("'", "").replace("`", "")
    token = re.sub(r"[^A-Za-z0-9]+", "", token)
    return token.lower()


def parse_author_name(value: Any) -> AuthorName | None:
    """Parse one author name string into surname and given-name tokens.

    Handles the four shapes this corpus actually contains: ``Surname, Given
    Middle``, ``Given Middle Surname``, dotted initial runs (``Perera, K.M.N.``)
    and the Vancouver style used by medical journals (``Perera KMN``). Returns
    ``None`` when nothing name-like survives cleaning.
    """

    if value is None:
        return None
    text = str(value)
    if not text.strip() or text.strip().casefold() in {"nan", "none", "null"}:
        return None

    text = INLINE_ORCID_RE.sub(" ", text)
    text = text.replace("*", " ").replace("†", " ").replace("‡", " ")
    text = WHITESPACE_RE.sub(" ", text.replace(" ", " ")).strip(" ,;.")
    if not text:
        return None

    while True:
        stripped = HONORIFIC_RE.sub("", text)
        if stripped == text:
            break
        text = stripped.strip()

    letters = [char for char in strip_accents(text) if char.isalpha()]
    # An all-uppercase string is a formatting artefact, not a signal that its
    # short tokens are initials, so the Vancouver rule below is disabled for it.
    is_all_upper = bool(letters) and all(char.isupper() for char in letters)

    # A trailing comma segment made only of degrees or generational suffixes
    # ("Sunil de Silva, PhD") qualifies the name rather than dividing it, so it
    # goes before the comma is read as a surname separator.
    segments = [segment.strip() for segment in text.split(",")]
    while len(segments) > 1 and _is_suffix_segment(segments[-1]):
        segments.pop()
    segments = [segment for segment in segments if segment]
    if not segments:
        return None

    initials_tail: list[str] = []
    if len(segments) > 1:
        surname_tokens = segments[0].split()
        given_tokens = " ".join(segments[1:]).split()
    else:
        tokens = _drop_suffix_tokens(segments[0].split())
        if not tokens:
            return None
        # Vancouver order puts the surname first and the initials last
        # ("Perera KMN", "de Silva S.P.").
        while len(tokens) > 1 and _is_initial_token(
            tokens[-1], previous=tokens[-2], is_all_upper=is_all_upper
        ):
            initials_tail.insert(0, tokens.pop())

        if initials_tail:
            surname_tokens, given_tokens = tokens, initials_tail
        elif len(tokens) == 1:
            surname_tokens, given_tokens = tokens, []
        else:
            surname_tokens = [tokens[-1]]
            remaining = tokens[:-1]
            while remaining and _normalize_token(remaining[-1]) in SURNAME_PARTICLES:
                surname_tokens.insert(0, remaining.pop())
            given_tokens = remaining

    given_tokens = _drop_suffix_tokens(given_tokens)
    surname_tokens = _drop_suffix_tokens(surname_tokens)
    if not surname_tokens:
        return None

    surname = "".join(_normalize_token(token) for token in surname_tokens)
    if not surname:
        return None

    given = _expand_given_tokens(
        given_tokens,
        is_all_upper=is_all_upper,
        # Tokens the Vancouver branch identified as a trailing initials run are
        # initials whatever the casing of the record.
        given_are_initials=bool(initials_tail),
    )
    display = _display_name(surname_tokens, given_tokens)

    return AuthorName(
        display=display,
        surname=surname,
        given=given,
        surname_display=" ".join(surname_tokens).strip(" ,.;"),
    )


def _drop_suffix_tokens(tokens: Sequence[str]) -> list[str]:
    kept = list(tokens)
    while kept and _normalize_token(kept[-1]) in SUFFIX_TOKENS:
        kept.pop()
    return kept


def _is_suffix_segment(segment: str) -> bool:
    tokens = [_normalize_token(token) for token in segment.split()]
    tokens = [token for token in tokens if token]
    return bool(tokens) and all(token in SUFFIX_TOKENS for token in tokens)


def _is_initial_token(token: str, *, previous: str, is_all_upper: bool) -> bool:
    """Whether a trailing token is a run of initials rather than a surname.

    In a mixed-case string an upper-case short token is a clear signal
    ("Perera KMN"). An entirely upper-cased string carries no case signal at
    all, so length decides: "SILVA AB" reads as a surname followed by initials,
    while "ANNE SILVA" -- whose last token is the longer one -- does not.
    """

    if DOTTED_INITIALS_RE.match(token.strip(" ,;")):
        return True
    cleaned = token.strip(" ,.;")
    if not cleaned.isalpha():
        return False
    if len(cleaned) == 1:
        return True
    if not is_all_upper:
        return cleaned.isupper() and len(cleaned) <= 4
    return len(cleaned) <= 3 and len(cleaned) < len(previous.strip(" ,.;"))


def _expand_given_tokens(
    tokens: Sequence[str], *, is_all_upper: bool, given_are_initials: bool = False
) -> tuple[str, ...]:
    """Turn given-name tokens into comparable units, splitting initial runs."""

    expanded: list[str] = []
    for token in tokens:
        cleaned = token.strip(" ,.;")
        if not cleaned:
            continue
        if given_are_initials or DOTTED_INITIALS_RE.match(token.strip(" ,;")):
            expanded.extend(char.lower() for char in cleaned if char.isalpha())
            continue
        normalized = _normalize_token(cleaned)
        if not normalized:
            continue
        # Vancouver style: "Perera KMN" packs the initials into one token. Only
        # applied to mixed-case strings, where an upper-case run is a real
        # signal rather than a side effect of an upper-cased record.
        if (
            not is_all_upper
            and 2 <= len(cleaned) <= 4
            and cleaned.isupper()
            and cleaned.isalpha()
        ):
            expanded.extend(normalized)
            continue
        expanded.append(normalized)
    return tuple(expanded)


def _display_name(surname_tokens: Sequence[str], given_tokens: Sequence[str]) -> str:
    surname = " ".join(surname_tokens).strip(" ,.;")
    given = " ".join(token.strip(" ,;") for token in given_tokens if token.strip(" ,.;"))
    return f"{surname}, {given}".strip(" ,") if given else surname


def author_variant_key(value: Any) -> str:
    """Stable key for one spelling of a name, used to key manual decisions."""

    name = parse_author_name(value)
    return name.variant_key if name else ""


def author_blocking_key(value: Any) -> str:
    """Surname plus first initial: the only candidates ever compared."""

    name = parse_author_name(value)
    return name.blocking_key if name else ""


def names_compatible(first: AuthorName, second: AuthorName) -> bool:
    """Whether two names could belong to one person.

    Compatible means: same surname, and no given-name position where both sides
    are spelled out and disagree. An initial matches a full name starting with
    that letter, and a missing middle name never blocks a match, because sources
    drop middle names freely.
    """

    if first.surname != second.surname:
        return False
    for left, right in zip(first.given, second.given):
        if len(left) == 1 or len(right) == 1:
            if left[0] != right[0]:
                return False
        elif left != right:
            return False
    return True


def name_is_more_specific(candidate: AuthorName, other: AuthorName) -> bool:
    """Whether ``candidate`` spells out a name that ``other`` only initials.

    Identical spellings never reach this function: they are the same variant by
    construction, which is why merging on the name alone means resolving an
    initialled form onto a spelled-out one rather than matching two equal
    strings.
    """

    return not candidate.is_initials_only and other.is_initials_only


# --- ORCID ------------------------------------------------------------------

def normalize_orcid(value: Any) -> str | None:
    """Return a validated ``0000-0002-1825-0097`` style ORCID, or ``None``.

    The final character is an ISO 7064 MOD 11-2 check digit, so a malformed or
    truncated identifier can be rejected outright rather than becoming a false
    identity anchor shared by unrelated authors.
    """

    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return None

    match = ORCID_RE.search(text)
    if not match:
        return None

    digits = "".join(match.group(index) for index in (1, 2, 3, 4))
    check = match.group(5).upper()
    if _orcid_check_digit(digits) != check:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}-{match.group(4)}{check}"


def _orcid_check_digit(digits: str) -> str:
    total = 0
    for char in digits:
        total = (total + int(char)) * 2
    remainder = total % 11
    result = (12 - remainder) % 11
    return "X" if result == 10 else str(result)


# --- record level extraction ------------------------------------------------

AUTHOR_NAME_COLUMNS = ("authors", "author_names")
INSTITUTION_ID_COLUMNS = ("national_institution_ids",)
INSTITUTION_NAME_COLUMNS = ("institutions", "author_affiliations")


@dataclass(frozen=True)
class AuthorMention:
    """One author position on one record."""

    position: int
    raw_name: str
    name: AuthorName
    orcid: str | None


def split_author_field(value: Any) -> list[str]:
    """Split an author list field into individual name strings.

    Semicolon, pipe and newline are unambiguous separators. A comma is only
    treated as one when there are enough of them to rule out ``Last, First``
    formatting, which is the same rule the extractors already apply.
    """

    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return []
    for separator in (";", "|", "\n"):
        if separator in text:
            return [part.strip() for part in text.split(separator) if part.strip()]
    if text.count(",") >= 3:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


def author_mentions(record: Mapping[str, Any]) -> list[AuthorMention]:
    """Extract parsed author positions, attaching an ORCID where it is safe to.

    An ORCID is attached only when it can be tied to a position without guessing:
    either it is written inline next to the name, or the record's ORCID list has
    exactly one entry per author. A mismatched list is dropped rather than
    aligned by luck -- a wrongly attached ORCID would merge two different people
    under the strongest rule in the system.
    """

    raw_names: list[str] = []
    for column in AUTHOR_NAME_COLUMNS:
        raw_names = split_author_field(record.get(column))
        if raw_names:
            break

    inline_orcids = [_inline_orcid(raw) for raw in raw_names]
    listed = [normalize_orcid(item) for item in split_author_field(record.get("author_orcids"))]
    listed = [orcid for orcid in listed if orcid]
    aligned = listed if len(listed) == len(raw_names) else []

    mentions: list[AuthorMention] = []
    for position, raw in enumerate(raw_names):
        name = parse_author_name(raw)
        if name is None:
            continue
        orcid = inline_orcids[position] or (aligned[position] if aligned else None)
        mentions.append(
            AuthorMention(position=position, raw_name=raw, name=name, orcid=orcid)
        )
    return mentions


def _inline_orcid(raw_name: str) -> str | None:
    match = INLINE_ORCID_RE.search(raw_name)
    return normalize_orcid(match.group(1)) if match else None


def record_institution_keys(record: Mapping[str, Any]) -> frozenset[str]:
    """Institution evidence keys for a record.

    Registry identifiers are preferred and prefixed ``id:``. Records the
    registry could not resolve still carry usable evidence, so their names are
    reduced with the registry's own lookup key and prefixed ``aff:`` -- an
    unresolved institution shared by two spellings of a name is the same signal,
    it just cannot be named canonically.
    """

    keys: set[str] = set()
    for column in INSTITUTION_ID_COLUMNS:
        for value in _split_semicolon(record.get(column)):
            keys.add(f"id:{value.strip()}")
    if keys:
        return frozenset(keys)

    for column in INSTITUTION_NAME_COLUMNS:
        for value in _split_semicolon(record.get(column)):
            key = normalize_lookup_key(value)
            if key:
                keys.add(f"aff:{key}")
    return frozenset(keys)


def _split_semicolon(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


# --- variant index ----------------------------------------------------------

@dataclass
class AuthorVariant:
    """Everything known about one spelling of one name, across the corpus."""

    variant_key: str
    blocking_key: str
    name: AuthorName
    display_names: Counter[str] = field(default_factory=Counter)
    orcids: set[str] = field(default_factory=set)
    institution_keys: set[str] = field(default_factory=set)
    coauthor_keys: set[str] = field(default_factory=set)
    mentions: int = 0
    records: list[str] = field(default_factory=list)
    years: set[int] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)

    @property
    def preferred_display(self) -> str:
        if not self.display_names:
            return self.name.display
        # Most frequent spelling wins; the longest breaks ties, so a fully
        # spelled-out form is preferred over an initialled one.
        return max(self.display_names.items(), key=lambda item: (item[1], len(item[0])))[0]


@dataclass
class VariantIndexStats:
    records: int = 0
    author_mentions: int = 0
    unparsed_names: int = 0
    mentions_with_orcid: int = 0
    records_with_orcid_field: int = 0
    records_with_aligned_orcids: int = 0
    invalid_orcids: int = 0
    records_with_institution_evidence: int = 0


class AuthorVariantIndex:
    """Accumulates author name variants and their evidence over a record stream.

    Aggregating at variant level rather than per author mention keeps memory
    bounded by the number of distinct spellings instead of the number of
    authorships, which is what makes a full-corpus run affordable.
    """

    def __init__(self) -> None:
        self.variants: dict[str, AuthorVariant] = {}
        self.blocks: dict[str, set[str]] = defaultdict(set)
        self.stats = VariantIndexStats()

    def add_record(self, record: Mapping[str, Any], *, record_id: str | None = None) -> list[str]:
        """Index one record; returns the variant keys of its authors, in order."""

        self.stats.records += 1

        raw_orcid_values = split_author_field(record.get("author_orcids"))
        if raw_orcid_values:
            self.stats.records_with_orcid_field += 1
            self.stats.invalid_orcids += sum(
                1 for value in raw_orcid_values if normalize_orcid(value) is None
            )

        mentions = author_mentions(record)
        raw_name_count = sum(
            len(split_author_field(record.get(column))) for column in AUTHOR_NAME_COLUMNS[:1]
        )
        self.stats.unparsed_names += max(raw_name_count - len(mentions), 0)
        if mentions and any(mention.orcid for mention in mentions):
            self.stats.records_with_aligned_orcids += 1

        institution_keys = record_institution_keys(record)
        if institution_keys:
            self.stats.records_with_institution_evidence += 1

        year = _parse_year(record.get("publication_year"))
        source = _clean_text(record.get("source_dataset"))
        blocking_keys = [mention.name.blocking_key for mention in mentions]
        identifier = record_id or _record_identifier(record, self.stats.records)

        keys: list[str] = []
        for mention in mentions:
            variant = self._variant(mention.name)
            variant.mentions += 1
            variant.display_names[mention.name.display] += 1
            self.stats.author_mentions += 1

            if mention.orcid:
                variant.orcids.add(mention.orcid)
                self.stats.mentions_with_orcid += 1
            variant.institution_keys |= institution_keys
            variant.coauthor_keys.update(
                key for key in blocking_keys if key and key != mention.name.blocking_key
            )
            if year is not None:
                variant.years.add(year)
            if source:
                variant.sources.add(source)
            if len(variant.records) < SAMPLE_RECORDS_PER_VARIANT:
                variant.records.append(identifier)
            keys.append(variant.variant_key)
        return keys

    def add_records(self, records: Iterable[Mapping[str, Any]]) -> None:
        for record in records:
            self.add_record(record)

    def _variant(self, name: AuthorName) -> AuthorVariant:
        variant = self.variants.get(name.variant_key)
        if variant is None:
            variant = AuthorVariant(
                variant_key=name.variant_key,
                blocking_key=name.blocking_key,
                name=name,
            )
            self.variants[name.variant_key] = variant
            self.blocks[name.blocking_key].add(name.variant_key)
        return variant


def _record_identifier(record: Mapping[str, Any], fallback_row: int) -> str:
    for column in ("record_number", "openalex_id", "doi", "source_record_id"):
        value = _clean_text(record.get(column))
        if value:
            return value
    return f"row:{fallback_row}"


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.casefold() == "nan":
        return None
    return text


def _parse_year(value: Any) -> int | None:
    text = _clean_text(value)
    if text is None:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


# --- manual decisions -------------------------------------------------------

@dataclass(frozen=True)
class AuthorDecision:
    """A reviewed verdict on one pair of name variants."""

    decision: str
    variant_key_a: str
    variant_key_b: str
    reviewer: str | None = None
    note: str | None = None

    @property
    def pair(self) -> tuple[str, str]:
        return tuple(sorted((self.variant_key_a, self.variant_key_b)))  # type: ignore[return-value]


DECISION_COLUMNS = ("decision", "variant_key_a", "variant_key_b", "reviewer", "note")


def load_author_decisions(path: str | Path) -> list[AuthorDecision]:
    """Read reviewed merge/split decisions. A missing file means no decisions."""

    decisions_path = Path(path)
    if not decisions_path.is_file():
        return []

    decisions: list[AuthorDecision] = []
    with decisions_path.open(newline="", encoding="utf-8") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            decision = (row.get("decision") or "").strip().casefold()
            key_a = (row.get("variant_key_a") or "").strip()
            key_b = (row.get("variant_key_b") or "").strip()
            if not decision and not key_a and not key_b:
                continue
            if decision not in DECISION_VALUES:
                raise ValueError(
                    f"{decisions_path}:{line_number}: decision must be one of "
                    f"{sorted(DECISION_VALUES)}, got {decision!r}"
                )
            if not key_a or not key_b or key_a == key_b:
                raise ValueError(
                    f"{decisions_path}:{line_number}: two different variant keys are required"
                )
            decisions.append(
                AuthorDecision(
                    decision=decision,
                    variant_key_a=key_a,
                    variant_key_b=key_b,
                    reviewer=(row.get("reviewer") or "").strip() or None,
                    note=(row.get("note") or "").strip() or None,
                )
            )
    return decisions


# --- clustering -------------------------------------------------------------

@dataclass
class AuthorCluster:
    """One resolved author identity."""

    author_id: str
    preferred_name: str
    surname: str
    variant_keys: tuple[str, ...]
    orcids: tuple[str, ...]
    institution_keys: tuple[str, ...]
    mentions: int
    match_method: str
    confidence: str
    review_reasons: tuple[str, ...]
    year_min: int | None
    year_max: int | None
    sources: tuple[str, ...]
    records: tuple[str, ...]
    merge_evidence: tuple[str, ...]

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    @property
    def national_institution_ids(self) -> tuple[str, ...]:
        return tuple(
            key.split(":", 1)[1] for key in self.institution_keys if key.startswith("id:")
        )


@dataclass
class AuthorReviewPair:
    """Two clusters that might be one person, queued for a human verdict."""

    blocking_key: str
    variant_key_a: str
    variant_key_b: str
    author_id_a: str
    author_id_b: str
    name_a: str
    name_b: str
    mentions_a: int
    mentions_b: int
    shared_institution_keys: tuple[str, ...]
    shared_coauthor_keys: tuple[str, ...]
    reasons: tuple[str, ...]
    records_a: tuple[str, ...]
    records_b: tuple[str, ...]

    @property
    def mentions(self) -> int:
        return self.mentions_a + self.mentions_b


@dataclass
class DisambiguationStats:
    variants: int = 0
    clusters: int = 0
    blocks: int = 0
    merges_by_method: Counter[str] = field(default_factory=Counter)
    clusters_by_method: Counter[str] = field(default_factory=Counter)
    clusters_by_confidence: Counter[str] = field(default_factory=Counter)
    orcid_blocked_merges: int = 0
    name_blocked_merges: int = 0
    decision_merges: int = 0
    decision_splits: int = 0
    manual_orcid_overrides: int = 0
    oversized_blocks: int = 0
    review_pairs: int = 0


@dataclass
class AuthorDisambiguationResult:
    clusters: dict[str, AuthorCluster]
    variant_to_author: dict[str, str]
    variant_match_method: dict[str, str]
    review_pairs: list[AuthorReviewPair]
    stats: DisambiguationStats

    def author_for(self, value: Any) -> AuthorCluster | None:
        """Resolve a raw name string to its cluster, for spot checks."""

        author_id = self.variant_to_author.get(author_variant_key(value))
        return self.clusters.get(author_id) if author_id else None


def disambiguate_authors(
    index: AuthorVariantIndex,
    *,
    decisions: Sequence[AuthorDecision] = (),
    min_shared_coauthors: int = 1,
    max_block_variants: int = DEFAULT_MAX_BLOCK_VARIANTS,
    max_review_roots_per_block: int = DEFAULT_MAX_REVIEW_ROOTS_PER_BLOCK,
) -> AuthorDisambiguationResult:
    """Cluster name variants into author identities using the documented rules."""

    builder = _ClusterBuilder(index.variants)
    stats = builder.stats
    stats.variants = len(index.variants)
    stats.blocks = len(index.blocks)

    # Splits are registered before anything merges, so a reviewed "different
    # people" verdict cannot be undone by a later automatic rule.
    for decision in decisions:
        if decision.decision == DECISION_DIFFERENT:
            builder.forbid(decision.variant_key_a, decision.variant_key_b)
            stats.decision_splits += 1

    _merge_on_orcid(index, builder)
    _merge_on_evidence(
        index,
        builder,
        min_shared_coauthors=min_shared_coauthors,
        max_block_variants=max_block_variants,
    )
    _merge_on_unique_name(index, builder, max_block_variants=max_block_variants)

    # Human verdicts run last and win, including over an ORCID conflict.
    for decision in decisions:
        if decision.decision == DECISION_SAME:
            if builder.merge(
                decision.variant_key_a,
                decision.variant_key_b,
                MATCH_METHOD_REVIEWED,
                forced=True,
            ):
                stats.decision_merges += 1

    clusters, variant_to_author, variant_method = builder.build()
    review_pairs = _review_pairs(
        index,
        builder,
        clusters,
        variant_to_author,
        decisions=decisions,
        max_review_roots_per_block=max_review_roots_per_block,
    )
    _clear_settled_review_reasons(clusters, review_pairs)
    stats.clusters = len(clusters)
    stats.review_pairs = len(review_pairs)
    for cluster in clusters.values():
        stats.clusters_by_method[cluster.match_method] += 1
        stats.clusters_by_confidence[cluster.confidence] += 1

    return AuthorDisambiguationResult(
        clusters=clusters,
        variant_to_author=variant_to_author,
        variant_match_method=variant_method,
        review_pairs=review_pairs,
        stats=stats,
    )


def _clear_settled_review_reasons(
    clusters: dict[str, AuthorCluster], review_pairs: Sequence[AuthorReviewPair]
) -> None:
    """Drop the contested-evidence flag once nothing is left to ask about.

    A spelling whose competing candidates have all been ruled on has no open
    question attached to it any more, so it should stop marking its records
    ambiguous. Reasons that describe how a cluster was built -- merged on the
    name alone, a manual override -- stay, because a decision does not change
    them.
    """

    contested = {
        key for pair in review_pairs for key in (pair.variant_key_a, pair.variant_key_b)
    }
    for author_id, cluster in clusters.items():
        if REVIEW_EVIDENCE_SEVERAL_PEOPLE not in cluster.review_reasons:
            continue
        if any(key in contested for key in cluster.variant_keys):
            continue
        clusters[author_id] = replace(
            cluster,
            review_reasons=tuple(
                reason
                for reason in cluster.review_reasons
                if reason != REVIEW_EVIDENCE_SEVERAL_PEOPLE
            ),
        )


def _merge_on_orcid(index: AuthorVariantIndex, builder: "_ClusterBuilder") -> None:
    """Rule 1: one ORCID, one person -- across surname blocks, so name changes
    and transliteration differences resolve too."""

    by_orcid: dict[str, list[str]] = defaultdict(list)
    for variant in index.variants.values():
        for orcid in variant.orcids:
            by_orcid[orcid].append(variant.variant_key)

    for variant_keys in by_orcid.values():
        anchor = variant_keys[0]
        for other in variant_keys[1:]:
            builder.merge(anchor, other, MATCH_METHOD_ORCID)


def _merge_on_evidence(
    index: AuthorVariantIndex,
    builder: "_ClusterBuilder",
    *,
    min_shared_coauthors: int,
    max_block_variants: int,
) -> None:
    """Rules 2-4, applied inside a surname block only."""

    for blocking_key, variant_keys in index.blocks.items():
        if len(variant_keys) > max_block_variants:
            builder.stats.oversized_blocks += 1
            builder.oversized_blocks.add(blocking_key)
            continue

        # Most-mentioned variants first, so the dominant spelling becomes the
        # anchor and the result does not depend on input order.
        ordered = sorted(
            variant_keys,
            key=lambda key: (-index.variants[key].mentions, key),
        )
        ambiguous = _ambiguous_initialled_variants(
            ordered, index, min_shared_coauthors=min_shared_coauthors
        )
        builder.ambiguous_initials |= ambiguous

        for position, key_a in enumerate(ordered):
            if key_a in ambiguous:
                continue
            variant_a = index.variants[key_a]
            for key_b in ordered[position + 1 :]:
                if key_b in ambiguous:
                    continue
                variant_b = index.variants[key_b]
                if builder.same_cluster(key_a, key_b):
                    continue
                if not names_compatible(variant_a.name, variant_b.name):
                    continue
                method = _evidence_method(
                    variant_a, variant_b, min_shared_coauthors=min_shared_coauthors
                )
                if method:
                    builder.merge(key_a, key_b, method)


def _ambiguous_initialled_variants(
    ordered: Sequence[str],
    index: AuthorVariantIndex,
    *,
    min_shared_coauthors: int,
) -> set[str]:
    """Initialled spellings whose evidence points at more than one person.

    "Perera, K." can share an institution with both "Perera, Kumara" and
    "Perera, Kamal". Merging into whichever the loop reaches first would be
    arbitrary, and merging into both would fuse two researchers, so the spelling
    is left on its own and queued for review.
    """

    ambiguous: set[str] = set()
    for key in ordered:
        variant = index.variants[key]
        if not variant.name.is_initials_only:
            continue

        candidates = [
            other
            for other in (index.variants[other_key] for other_key in ordered if other_key != key)
            if not other.name.is_initials_only
            and names_compatible(variant.name, other.name)
            and _evidence_method(variant, other, min_shared_coauthors=min_shared_coauthors)
        ]
        if any(
            not names_compatible(first.name, second.name)
            for position, first in enumerate(candidates)
            for second in candidates[position + 1 :]
        ):
            ambiguous.add(key)
    return ambiguous


def _evidence_method(
    variant_a: AuthorVariant,
    variant_b: AuthorVariant,
    *,
    min_shared_coauthors: int,
) -> str | None:
    if variant_a.institution_keys & variant_b.institution_keys:
        return MATCH_METHOD_AFFILIATION
    shared_coauthors = variant_a.coauthor_keys & variant_b.coauthor_keys
    if len(shared_coauthors) >= max(min_shared_coauthors, 1):
        return MATCH_METHOD_COAUTHOR
    return None


def _merge_on_unique_name(
    index: AuthorVariantIndex,
    builder: "_ClusterBuilder",
    *,
    max_block_variants: int,
) -> None:
    """Rule 4: resolve an initialled name onto the one spelled-out name it fits.

    Applied only when the block leaves no choice -- exactly one spelled-out
    cluster is compatible -- and only when nothing contradicts it. Two clusters
    that both know their institutions and share none are left apart for review
    instead: a wrong merge here would silently fuse two researchers, while
    leaving them apart merely leaves a question open.
    """

    for blocking_key, variant_keys in index.blocks.items():
        if blocking_key in builder.oversized_blocks or len(variant_keys) > max_block_variants:
            continue

        by_root: dict[str, list[AuthorVariant]] = defaultdict(list)
        for key in variant_keys:
            by_root[builder.find(key)].append(index.variants[key])
        if len(by_root) < 2:
            continue

        primaries = {root: _primary(variants) for root, variants in by_root.items()}
        institutions = {
            root: {key for variant in variants for key in variant.institution_keys}
            for root, variants in by_root.items()
        }

        initialled = sorted(
            (root for root, primary in primaries.items() if primary.name.is_initials_only),
            key=lambda root: (-sum(variant.mentions for variant in by_root[root]), root),
        )
        for root in initialled:
            primary = primaries[root]
            if primary.variant_key in builder.ambiguous_initials:
                continue
            candidates = [
                other
                for other, other_primary in primaries.items()
                if other != root
                and name_is_more_specific(other_primary.name, primary.name)
                and names_compatible(primary.name, other_primary.name)
            ]
            if len(candidates) != 1:
                continue

            target = candidates[0]
            if builder.same_cluster(primary.variant_key, primaries[target].variant_key):
                continue
            if (
                institutions[root]
                and institutions[target]
                and institutions[root].isdisjoint(institutions[target])
            ):
                continue
            builder.merge(primary.variant_key, primaries[target].variant_key, MATCH_METHOD_NAME)


class _ClusterBuilder:
    """Union-find over variant keys with ORCID and reviewer constraints."""

    def __init__(self, variants: Mapping[str, AuthorVariant]) -> None:
        self.variants = variants
        self.parent: dict[str, str] = {key: key for key in variants}
        self.members: dict[str, list[str]] = {key: [key] for key in variants}
        self.orcids: dict[str, set[str]] = {
            key: set(variant.orcids) for key, variant in variants.items()
        }
        self.forbidden: dict[str, set[str]] = defaultdict(set)
        # Variants whose given names are spelled out, per cluster. Two of these
        # that disagree are two people, so they gate every later merge.
        self.specific: dict[str, list[str]] = {
            key: ([] if variant.name.is_initials_only else [key])
            for key, variant in variants.items()
        }
        self.method: dict[str, str] = {key: MATCH_METHOD_SINGLETON for key in variants}
        self.merge_log: dict[str, list[str]] = defaultdict(list)
        self.overrides: dict[str, list[str]] = defaultdict(list)
        self.oversized_blocks: set[str] = set()
        self.ambiguous_initials: set[str] = set()
        self.stats = DisambiguationStats()

    def find(self, key: str) -> str:
        root = self.parent.get(key, key)
        while root != self.parent.get(root, root):
            self.parent[root] = self.parent.get(self.parent[root], self.parent[root])
            root = self.parent[root]
        self.parent[key] = root
        return root

    def same_cluster(self, key_a: str, key_b: str) -> bool:
        return key_a in self.parent and key_b in self.parent and self.find(key_a) == self.find(key_b)

    def forbid(self, key_a: str, key_b: str) -> None:
        self.forbidden[key_a].add(key_b)
        self.forbidden[key_b].add(key_a)

    def merge(self, key_a: str, key_b: str, method: str, *, forced: bool = False) -> bool:
        if key_a not in self.parent or key_b not in self.parent:
            return False
        root_a, root_b = self.find(key_a), self.find(key_b)
        if root_a == root_b:
            return False

        orcid_conflict = (
            bool(self.orcids[root_a])
            and bool(self.orcids[root_b])
            and self.orcids[root_a].isdisjoint(self.orcids[root_b])
        )
        reviewer_conflict = self._reviewer_conflict(root_a, root_b)
        # An initialled name can be compatible with two spelled-out names that
        # are not compatible with each other ("Perera, K." fits both "Kumara"
        # and "Kamal"). Without this gate the shared initial would drag them
        # into one identity by transitivity. ORCID and reviewed merges are
        # exempt: both are stronger evidence than a spelling.
        name_conflict = method != MATCH_METHOD_ORCID and self._name_conflict(root_a, root_b)
        if not forced and (orcid_conflict or reviewer_conflict or name_conflict):
            if orcid_conflict:
                self.stats.orcid_blocked_merges += 1
            elif name_conflict:
                self.stats.name_blocked_merges += 1
            return False
        if forced and reviewer_conflict:
            # Contradictory decisions: a split already covers this pair.
            return False

        # Keep the larger cluster as the root so the union stays shallow.
        if len(self.members[root_a]) < len(self.members[root_b]):
            root_a, root_b = root_b, root_a

        self.parent[root_b] = root_a
        self.members[root_a].extend(self.members.pop(root_b))
        self.orcids[root_a] |= self.orcids.pop(root_b)
        self.specific[root_a].extend(self.specific.pop(root_b, []))
        self.method[root_a] = _strongest_method(
            self.method[root_a], self.method.pop(root_b), method
        )
        self.merge_log[root_a].extend(self.merge_log.pop(root_b, []))
        self.merge_log[root_a].append(f"{key_a}+{key_b}:{method}")
        self.overrides[root_a].extend(self.overrides.pop(root_b, []))
        if forced and orcid_conflict:
            self.overrides[root_a].append(REVIEW_MANUAL_ORCID_OVERRIDE)
            self.stats.manual_orcid_overrides += 1
        self.stats.merges_by_method[method] += 1
        return True

    def _reviewer_conflict(self, root_a: str, root_b: str) -> bool:
        members_b = set(self.members[root_b])
        return any(self.forbidden.get(member, set()) & members_b for member in self.members[root_a])

    def _name_conflict(self, root_a: str, root_b: str) -> bool:
        """Whether the two clusters hold spelled-out names that disagree.

        Only names sharing a surname are compared: a merge across surnames can
        only come from an ORCID or a reviewer, and both outrank a spelling.
        """

        for key_a in self.specific[root_a]:
            name_a = self.variants[key_a].name
            for key_b in self.specific[root_b]:
                name_b = self.variants[key_b].name
                if name_a.surname == name_b.surname and not names_compatible(name_a, name_b):
                    return True
        return False

    def build(self) -> tuple[dict[str, AuthorCluster], dict[str, str], dict[str, str]]:
        clusters: dict[str, AuthorCluster] = {}
        variant_to_author: dict[str, str] = {}
        variant_method: dict[str, str] = {}

        for root, member_keys in self.members.items():
            if self.find(root) != root:
                continue
            members = [self.variants[key] for key in member_keys]
            orcids = tuple(sorted(self.orcids[root]))
            # An ORCID anchors the identity whether or not it is what merged the
            # cluster, so it is what the cluster reports as its evidence --
            # unless a reviewer settled it, which outranks even that.
            method = (
                _strongest_method(self.method[root], MATCH_METHOD_ORCID)
                if orcids
                else self.method[root]
            )
            author_id = _author_id(orcids, member_keys)
            primary = max(members, key=lambda variant: (variant.mentions, len(variant.name.display)))

            institution_keys = sorted(
                {key for variant in members for key in variant.institution_keys}
            )
            years = sorted({year for variant in members for year in variant.years})
            reasons: list[str] = sorted(set(self.overrides.get(root, [])))
            if method == MATCH_METHOD_NAME:
                reasons.append(REVIEW_MERGED_ON_NAME_ONLY)
            if not orcids and all(variant.name.is_initials_only for variant in members):
                reasons.append(REVIEW_INITIALS_ONLY)
            if any(key in self.ambiguous_initials for key in member_keys):
                reasons.append(REVIEW_EVIDENCE_SEVERAL_PEOPLE)
            if primary.blocking_key in self.oversized_blocks:
                reasons.append(REVIEW_OVERSIZED_BLOCK)

            clusters[author_id] = AuthorCluster(
                author_id=author_id,
                preferred_name=primary.preferred_display,
                surname=primary.name.surname_display,
                variant_keys=tuple(sorted(member_keys)),
                orcids=orcids,
                institution_keys=tuple(institution_keys),
                mentions=sum(variant.mentions for variant in members),
                match_method=method,
                confidence="high" if orcids else CONFIDENCE_BY_METHOD[method],
                review_reasons=tuple(dict.fromkeys(reasons)),
                year_min=years[0] if years else None,
                year_max=years[-1] if years else None,
                sources=tuple(sorted({source for variant in members for source in variant.sources})),
                records=tuple(
                    record for variant in members for record in variant.records
                )[:SAMPLE_RECORDS_PER_VARIANT],
                merge_evidence=tuple(self.merge_log.get(root, [])[:20]),
            )
            for key in member_keys:
                variant_to_author[key] = author_id
                variant_method[key] = method
        return clusters, variant_to_author, variant_method


def _strongest_method(*methods: str) -> str:
    return max(methods, key=lambda method: MATCH_METHOD_PRECEDENCE.index(method))


def _author_id(orcids: Sequence[str], variant_keys: Sequence[str]) -> str:
    """Derive a stable identifier from the cluster's anchor.

    The anchor is the cluster's lowest ORCID, or its lowest variant key when it
    has none, so an author keeps the same identifier between runs as long as
    that anchor keeps resolving to them.
    """

    anchor = f"orcid:{min(orcids)}" if orcids else f"name:{min(variant_keys)}"
    return "A" + hashlib.sha1(anchor.encode("utf-8")).hexdigest()[:11].upper()


def _review_pairs(
    index: AuthorVariantIndex,
    builder: _ClusterBuilder,
    clusters: Mapping[str, AuthorCluster],
    variant_to_author: Mapping[str, str],
    *,
    decisions: Sequence[AuthorDecision],
    max_review_roots_per_block: int,
) -> list[AuthorReviewPair]:
    """Queue compatible-but-unmerged clusters for a human verdict.

    These are the records the rules could not settle: the names could belong to
    one person, but no ORCID, affiliation or coauthor connects them. Pairs a
    reviewer has already ruled on are left out, and pairs with conflicting
    ORCIDs are not queued at all -- those are settled, not ambiguous.
    """

    decided = {decision.pair for decision in decisions}
    pairs: list[AuthorReviewPair] = []

    for blocking_key, variant_keys in index.blocks.items():
        by_root: dict[str, list[AuthorVariant]] = defaultdict(list)
        for key in variant_keys:
            by_root[builder.find(key)].append(index.variants[key])
        if len(by_root) < 2:
            continue

        roots = sorted(
            by_root,
            key=lambda root: -sum(variant.mentions for variant in by_root[root]),
        )[:max_review_roots_per_block]

        for position, root_a in enumerate(roots):
            primary_a = _primary(by_root[root_a])
            for root_b in roots[position + 1 :]:
                primary_b = _primary(by_root[root_b])
                if not names_compatible(primary_a.name, primary_b.name):
                    continue
                if (
                    builder.orcids[root_a]
                    and builder.orcids[root_b]
                    and builder.orcids[root_a].isdisjoint(builder.orcids[root_b])
                ):
                    continue
                pair_key = tuple(sorted((primary_a.variant_key, primary_b.variant_key)))
                if pair_key in decided:
                    continue

                contested = {primary_a.variant_key, primary_b.variant_key} & builder.ambiguous_initials
                reasons = [
                    REVIEW_EVIDENCE_SEVERAL_PEOPLE
                    if contested
                    else REVIEW_COMPATIBLE_NAMES_NO_EVIDENCE
                ]
                if primary_a.name.is_initials_only or primary_b.name.is_initials_only:
                    reasons.append(REVIEW_INITIALS_ONLY)
                if blocking_key in builder.oversized_blocks:
                    reasons.append(REVIEW_OVERSIZED_BLOCK)

                pairs.append(
                    AuthorReviewPair(
                        blocking_key=blocking_key,
                        variant_key_a=primary_a.variant_key,
                        variant_key_b=primary_b.variant_key,
                        author_id_a=variant_to_author[primary_a.variant_key],
                        author_id_b=variant_to_author[primary_b.variant_key],
                        name_a=primary_a.preferred_display,
                        name_b=primary_b.preferred_display,
                        mentions_a=sum(variant.mentions for variant in by_root[root_a]),
                        mentions_b=sum(variant.mentions for variant in by_root[root_b]),
                        shared_institution_keys=tuple(
                            sorted(primary_a.institution_keys & primary_b.institution_keys)
                        ),
                        shared_coauthor_keys=tuple(
                            sorted(primary_a.coauthor_keys & primary_b.coauthor_keys)
                        ),
                        reasons=tuple(reasons),
                        records_a=tuple(primary_a.records),
                        records_b=tuple(primary_b.records),
                    )
                )

    pairs.sort(key=lambda pair: (-pair.mentions, pair.variant_key_a, pair.variant_key_b))
    return pairs


def _primary(variants: Sequence[AuthorVariant]) -> AuthorVariant:
    return max(variants, key=lambda variant: (variant.mentions, len(variant.name.display)))
