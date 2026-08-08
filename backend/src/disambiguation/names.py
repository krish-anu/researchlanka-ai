"""
Personal-name normalization, parsing and blocking.

Everything downstream of this module compares *parsed* names, never raw
strings. The corpus carries the same person as "T.K.K. Chamindu Deepagoda",
"Deepagoda, T.K.K.C." and "Chamindu Deepagoda Thuduwe", so a raw-string
equality test both misses matches and cannot express partial evidence.

Two properties of the merged dataset shape the design:

  * The `authors` field is semicolon-joined by `unique_join`, so semicolons are
    the record separator and any comma inside a segment is name-internal
    ("Surname, Initials" from repository records).
  * Some records carry name *fragments* alongside the full name — one row lists
    "Gyan Prasad Bajgai", "Gyan Prasad", "Sangay Bajgai" and "Birendra" for a
    five-author paper. These are an upstream artefact, not extra people, and
    `drop_intra_record_fragments` removes them before clustering so they do not
    manufacture authors.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

__all__ = [
    "ParsedName",
    "blocking_key",
    "drop_intra_record_fragments",
    "name_compatibility",
    "normalize_name_text",
    "parse_name",
    "split_names",
]


# Particles stay attached to the surname: "de Silva" and "van der Berg" are one
# surname, and splitting them turns a common Sri Lankan name into a given name.
SURNAME_PARTICLES = {
    "de", "del", "della", "der", "di", "du", "la", "le", "van", "von", "bin",
    "binti", "al", "el", "da", "dos", "das", "st",
}

# Honorifics and suffixes carry no identity and collide across people.
#
# Several of these are also perfectly ordinary initial runs: MS, ER, MD, II.
# `_is_initial_token` guards against stripping those — see the note there.
HONORIFICS = {
    "dr", "prof", "professor", "mr", "mrs", "ms", "miss", "rev", "ven", "sir",
    "eng", "er", "assoc", "asst", "snr", "jnr",
}
SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "phd", "md", "msc", "bsc", "mbbs"}

_NON_NAME_CHARS = re.compile(r"[^\w\s.,'\-]", re.UNICODE)
_MULTI_SPACE = re.compile(r"\s+")
_INITIAL_RUN = re.compile(r"^(?:[A-Za-z]\.){2,}$")


def strip_accents(text: str) -> str:
    """Fold diacritics so "Perera" and "Pereră" block together."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _clean_preserving_case(value: str) -> str:
    """Accent-folded and punctuation-tamed, but still in its original case.

    Case survives this step because `_is_initial_token` needs it: once the
    string is casefolded, "MS" (initials) and "Ms" (honorific) are the same
    token and the distinction is gone for good.
    """
    text = _NON_NAME_CHARS.sub(" ", strip_accents(str(value)))
    return _MULTI_SPACE.sub(" ", text).strip()


def normalize_name_text(value: str) -> str:
    """Casefolded, accent-folded, punctuation-tamed form used for all keys."""
    return _clean_preserving_case(value).casefold()


def split_names(value: object) -> list[str]:
    """
    Split a merged author field into individual name strings.

    Semicolon only. A comma is name-internal in this dataset, so splitting on
    it would turn "Deepagoda, T.K.K.C." into two authors.
    """
    if value is None:
        return []
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null", "na", "n/a", "[]"}:
        return []
    return [part.strip() for part in text.split(";") if part.strip()]


def _expand_initial_run(token: str) -> list[str]:
    """"T.K.K." -> ["t", "k", "k"]; a single "T." stays one initial."""
    if _INITIAL_RUN.match(token):
        return [char.casefold() for char in token if char.isalpha()]
    return [token]


def _is_initial_token(token: str) -> bool:
    """
    Whether an original-case token reads as initials rather than a word.

    This exists because the honorific list overlaps the initial space: "MS
    Perera" is M.S. Perera, and "Perera, JNR" is Perera, J.N.R. — but "ms" and
    "jnr" are also honorifics. Stripping them leaves a bare surname, and every
    such name in the corpus then collapses into one enormous false identity.
    Measured on the corpus, this merged 1,575 publications under a single
    "Perera" before the guard was added.

    An all-uppercase token with no lowercase letters is read as initials. The
    remaining error is an all-caps name like "DR W PERERA", where "DR" is read
    as initials. That over-splits by one identity, which is the safe direction:
    a split identity is visible and reviewable, a false merge is not.
    """
    stripped = token.strip(".-'")
    return bool(stripped) and stripped.isupper() and stripped.isalpha()


@dataclass(frozen=True)
class ParsedName:
    """A name decomposed into the parts that carry identity."""

    raw: str
    surname: str
    given: tuple[str, ...] = ()
    """Given-name tokens, full words only (initials are held separately)."""
    initials: tuple[str, ...] = ()
    """First letters of every given token, in order, including bare initials."""
    dropped_tokens: tuple[str, ...] = field(default=(), repr=False)

    @property
    def is_surname_only(self) -> bool:
        return not self.initials

    @property
    def has_full_given_name(self) -> bool:
        return bool(self.given)

    @property
    def normalized(self) -> str:
        """
        Exact identity key for this spelling. Not a display string.

        It must keep given names and initials separate: collapsing "Wimal
        Perera" and "W. Perera" to the same key would merge them with no
        evidence at all, which is the exact failure this module exists to
        prevent. The two are compared by `name_compatibility` instead.
        """
        return f"{self.surname}|{' '.join(self.given)}|{''.join(self.initials)}"

    @property
    def token_set(self) -> frozenset[str]:
        """All full-word tokens, for fragment detection."""
        return frozenset({self.surname, *self.given}) - {""}


def parse_name(raw: str) -> ParsedName | None:
    """
    Parse one name string into surname / given names / initials.

    Returns None when nothing usable survives normalization (empty strings,
    pure punctuation, bare honorifics).
    """
    # Case is preserved through tokenizing so honorifics can be told apart from
    # initials, then folded once the decision is made.
    text = _clean_preserving_case(raw)
    if not text:
        return None

    # "Surname, Given" — the comma is authoritative when it splits the string
    # into exactly two non-empty halves.
    if text.count(",") == 1:
        head, tail = (part.strip() for part in text.split(","))
        if head and tail:
            text = f"{tail} {head}"
    text = text.replace(",", " ")

    raw_tokens = [token for token in _MULTI_SPACE.split(text) if token]
    tokens: list[str] = []
    dropped: list[str] = []
    for token in raw_tokens:
        stripped = token.strip(".-'")
        if not stripped:
            continue
        folded = stripped.casefold()
        if (folded in HONORIFICS or folded in SUFFIXES) and not _is_initial_token(token):
            dropped.append(folded)
            continue
        tokens.extend(_expand_initial_run(token))

    tokens = [token.strip(".-'").casefold() for token in tokens]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None

    # Pull the surname off the end, absorbing any particle run before it.
    surname_parts = [tokens.pop()]
    while tokens and tokens[-1] in SURNAME_PARTICLES:
        surname_parts.insert(0, tokens.pop())
    surname = " ".join(surname_parts)

    given = tuple(token for token in tokens if len(token) > 1)
    initials = tuple(token[0] for token in tokens if token)

    return ParsedName(
        raw=str(raw).strip(),
        surname=surname,
        given=given,
        initials=initials,
        dropped_tokens=tuple(dropped),
    )


def blocking_key(parsed: ParsedName) -> str:
    """
    Candidate-generation key: surname plus first given initial.

    This is the standard bibliometric block. It is deliberately loose — it must
    not separate "W. Perera" from "Wimal Perera", because the scoring stage can
    reject a bad pair but can never recover one that was never compared.
    Surname-only mentions get their own block so they are never silently merged
    into a named person.
    """
    if parsed.is_surname_only:
        return f"{parsed.surname}|_"
    return f"{parsed.surname}|{parsed.initials[0]}"


def name_compatibility(left: ParsedName, right: ParsedName) -> float:
    """
    How well two names agree, on 0..1. This is *not* a probability that they
    are the same person — it is one input to that decision.

      1.0  identical full given names
      0.8  one side abbreviates the other ("Wimal Perera" vs "W. Perera")
      0.0  a direct conflict (different full given names, or clashing initials)

    Different surnames always score 0: this function is only ever called on
    within-block pairs, where surnames already agree.
    """
    if left.surname != right.surname:
        return 0.0

    # Initials must not contradict where both sides have them.
    shared = min(len(left.initials), len(right.initials))
    if shared and left.initials[:shared] != right.initials[:shared]:
        return 0.0

    if left.given and right.given:
        if left.given == right.given:
            return 1.0
        # One given-name list extending the other is agreement, not conflict
        # ("Chamindu" vs "Chamindu Deepagoda").
        short, long = sorted((left.given, right.given), key=len)
        if long[: len(short)] == short:
            return 0.9
        # Same first given name but a different middle name is weak agreement.
        if left.given[0] == right.given[0]:
            return 0.6
        return 0.0

    # At least one side is initials-only.
    if not left.initials or not right.initials:
        return 0.3  # a surname-only mention agrees with everything, weakly
    if len(left.initials) != len(right.initials):
        return 0.7
    return 0.8


def drop_intra_record_fragments(
    parsed_names: list[ParsedName],
) -> tuple[list[ParsedName], list[ParsedName]]:
    """
    Remove name fragments that appear alongside their own full name.

    A mention is a fragment when its full-word tokens are a strict subset of
    another mention's tokens *in the same record* — "Gyan Prasad" beside "Gyan
    Prasad Bajgai". Roughly 90% of records with ORCIDs carry this artefact, and
    left in place each fragment becomes a phantom author.

    Surname-only and initials-only mentions are never treated as fragments:
    "W. Perera" beside "Wimal Perera" is far more likely to be the same person
    written twice than evidence of a subset relationship worth deleting, and
    dropping it would lose a real mention. The clustering stage merges those.
    """
    kept: list[ParsedName] = []
    dropped: list[ParsedName] = []

    token_sets = [name.token_set for name in parsed_names]
    for index, name in enumerate(parsed_names):
        tokens = token_sets[index]
        if len(tokens) < 2:
            kept.append(name)
            continue
        is_fragment = any(
            other_index != index and tokens < other_tokens
            for other_index, other_tokens in enumerate(token_sets)
        )
        (dropped if is_fragment else kept).append(name)

    return kept, dropped
