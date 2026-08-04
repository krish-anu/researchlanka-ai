"""Publication type and venue standardization.

Source systems describe the same output in many ways: OpenAlex says
``journal-article``, Crossref says ``article``, and university repositories say
``Article-Full-text``. This module maps all of them onto one controlled
vocabulary.

Standardizing naively would destroy information, because repository type values
encode three separate facts in one string. ``Thesis-Abstract`` says the genre is
a thesis, the record holds only an abstract, and the degree level is unstated.
Each fact is therefore extracted into its own field rather than collapsed away:

- ``publication_type`` -- the genre, from :data:`PUBLICATION_TYPES`
- ``record_form`` -- whether the record is full text or an abstract only
- ``thesis_degree_level`` -- masters / mphil / phd, where stated
- ``is_research_output`` -- False for exam papers, front matter and media
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


PUBLICATION_TYPES = frozenset(
    {
        "journal_article",
        "conference_paper",
        "proceedings",
        "thesis",
        "book",
        "book_chapter",
        "book_review",
        "report",
        "preprint",
        "dataset",
        "software",
        "review",
        "peer_review",
        "editorial",
        "letter",
        "erratum",
        "retraction",
        "reference_entry",
        "supplementary_material",
        "abstract",
        "presentation",
        "exam_paper",
        "journal_issue",
        "paratext",
        "media",
        "non_research",
        "unknown",
    }
)

# Types that do not represent a research output. Excluded from research counts
# while remaining in the dataset, so nothing is silently lost.
NON_RESEARCH_TYPES = frozenset(
    {"exam_paper", "journal_issue", "paratext", "media", "non_research", "unknown"}
)

RECORD_FORMS = frozenset({"full_text", "abstract", "unknown"})
THESIS_DEGREE_LEVELS = frozenset({"masters", "mphil", "phd", "unknown"})

# Exact matches on the normalized value, checked before keyword rules.
TYPE_ALIASES: dict[str, str] = {
    # Journal articles
    "article": "journal_article",
    "journal article": "journal_article",
    "journal": "journal_article",
    "research paper": "journal_article",
    "research article": "journal_article",
    "full paper": "journal_article",
    "technical paper": "journal_article",
    "short communication": "journal_article",
    "data paper": "journal_article",
    "software paper": "journal_article",
    "a": "unknown",
    "p": "unknown",
    # Conference outputs
    "conference paper": "conference_paper",
    "conference": "conference_paper",
    "conferenece paper": "conference_paper",
    "confence paper": "conference_paper",
    "proceedings article": "conference_paper",
    "proceedings": "proceedings",
    "preliminary pages of the proceeding book": "paratext",
    # Theses
    "thesis": "thesis",
    "theses": "thesis",
    "dissertation": "thesis",
    # Books
    "book": "book",
    "e book": "book",
    "book chapter": "book_chapter",
    "e book chapter": "book_chapter",
    "book review": "book_review",
    "book part": "book_chapter",
    # Reports
    "report": "report",
    "technical report": "report",
    "src report": "report",
    "working paper": "report",
    # Other scholarly records
    "preprint": "preprint",
    "posted content": "preprint",
    "dataset": "dataset",
    "software": "software",
    "review": "review",
    "peer review": "peer_review",
    "editorial": "editorial",
    "letter": "letter",
    "erratum": "erratum",
    "correction": "erratum",
    "retraction": "retraction",
    "reference entry": "reference_entry",
    "supplementary materials": "supplementary_material",
    "supplementary material": "supplementary_material",
    "journal issue": "journal_issue",
    "abstract": "abstract",
    "research abstract": "abstract",
    # Presentations and speeches
    "presentation": "presentation",
    "guest speech": "presentation",
    "keynote speech": "presentation",
    "convocation speach": "presentation",
    "convocation speech": "presentation",
    "recording oral": "presentation",
    # Teaching and administrative material
    "exam paper": "exam_paper",
    "learning object": "media",
    "animation": "media",
    "video": "media",
    "image": "media",
    "paratext": "paratext",
    "contents": "paratext",
    "pre text": "paratext",
    "convocation booklet": "non_research",
    "felicitation": "non_research",
    "other": "unknown",
    "": "unknown",
}

# Fallback keyword rules, longest phrase first so "book chapter" beats "book".
TYPE_KEYWORD_RULES: tuple[tuple[str, str], ...] = (
    ("book chapter", "book_chapter"),
    ("book review", "book_review"),
    ("conference", "conference_paper"),
    ("proceeding", "proceedings"),
    ("thesis", "thesis"),
    ("theses", "thesis"),
    ("dissertation", "thesis"),
    ("exam", "exam_paper"),
    ("report", "report"),
    ("preprint", "preprint"),
    ("dataset", "dataset"),
    ("software", "software"),
    ("speech", "presentation"),
    ("presentation", "presentation"),
    ("book", "book"),
    ("journal", "journal_article"),
    ("article", "journal_article"),
    ("abstract", "abstract"),
)

FULL_TEXT_MARKERS = ("full text", "fulltext", "full paper")
ABSTRACT_MARKERS = ("abstract",)
EXTENDED_ABSTRACT_MARKERS = ("extended abstract",)

DEGREE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(?:ph\s*d|phd|doctoral|doctorate)\b", re.IGNORECASE), "phd"),
    (re.compile(r"\bm\s*\.?\s*(?:phil|pil)\b", re.IGNORECASE), "mphil"),
    (re.compile(r"\bmphil\b", re.IGNORECASE), "mphil"),
    (re.compile(r"\bmaster(?:s|'s)?\b", re.IGNORECASE), "masters"),
    (re.compile(r"\bm\s*\.?\s*sc\b", re.IGNORECASE), "masters"),
)

SEPARATOR_RE = re.compile(r"[-_/.,]+")
WHITESPACE_RE = re.compile(r"\s+")

# Venue names that identify a platform rather than a journal. Matched as
# substrings of the lowercased venue name.
VENUE_TYPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        ("arxiv", "biorxiv", "medrxiv", "chemrxiv", "psyarxiv", "techrxiv", "preprints.org",
         "research square", "ssrn", "social science research network", "authorea", "osf preprints"),
        "preprint_server",
    ),
    (
        ("zenodo", "figshare", "dryad", "archaeology data service", "data service",
         "cgspace", "dataverse"),
        "data_repository",
    ),
    (
        ("repository", "research online", "eprints", "institutional repository",
         "profiles and research", "ssoar"),
        "institutional_repository",
    ),
    (
        ("hal (le centre", "communication scientifique directe", "pubmed", "europe pmc",
         "researchgate", "semantic scholar"),
        "aggregator",
    ),
    # "proceedings" is deliberately absent: it appears in journal titles such as
    # "Proceedings of the National Academy of Sciences". Genuine conference
    # venues in this corpus all carry one of the words below as well.
    (("conference", "symposium", "workshop", "congress"), "conference"),
    (("ebooks", "e-books", "ebook series", "book series"), "book_series"),
)

JOURNAL_NAME_HINTS = (
    "journal", "review", "letters", "proceedings", "bulletin", "annals",
    "transactions", "quarterly", "reports", "archives", "acta", "studies",
)

TRAILING_PARENTHETICAL_RE = re.compile(r"\s*\(([^()]*)\)\s*$")

# Words that mark a trailing parenthetical as a publisher or host organisation
# rather than part of the venue's own name.
ORGANISATION_MARKERS = (
    "university", "universite", "universidad", "publisher", "publishing", "press",
    "ltd", "inc", "llc", "gmbh", "society", "association", "organization",
    "organisation", "foundation", "laboratory", "cern", "company", "group",
    "elsevier", "springer", "wiley", "taylor", "francis", "sage", "college",
    "school", "academy", "council", "centre for", "center for", "part of",
)


@dataclass(frozen=True)
class StandardizedType:
    """The facts recovered from one raw publication-type string."""

    publication_type: str
    record_form: str
    thesis_degree_level: str
    is_research_output: bool


def standardize_publication_type(value: Any) -> StandardizedType:
    """Split a raw type string into genre, record form and degree level."""

    normalized = _normalize_type_text(value)

    record_form = "unknown"
    if any(marker in normalized for marker in FULL_TEXT_MARKERS):
        record_form = "full_text"
    elif any(marker in normalized for marker in ABSTRACT_MARKERS):
        record_form = "abstract"

    degree_level = "unknown"
    for pattern, level in DEGREE_RULES:
        if pattern.search(normalized):
            degree_level = level
            break

    publication_type = _resolve_type(normalized, record_form)
    if degree_level != "unknown" and publication_type in {"unknown", "abstract"}:
        publication_type = "thesis"
    if publication_type != "thesis":
        degree_level = "unknown"

    return StandardizedType(
        publication_type=publication_type,
        record_form=record_form,
        thesis_degree_level=degree_level,
        is_research_output=publication_type not in NON_RESEARCH_TYPES,
    )


def _resolve_type(normalized: str, record_form: str) -> str:
    if normalized in TYPE_ALIASES:
        return TYPE_ALIASES[normalized]

    # Strip the form marker so "thesis full text" resolves like "thesis".
    stem = normalized
    for marker in EXTENDED_ABSTRACT_MARKERS + FULL_TEXT_MARKERS + ABSTRACT_MARKERS:
        stem = stem.replace(marker, " ")
    stem = WHITESPACE_RE.sub(" ", stem).strip()

    if stem in TYPE_ALIASES:
        return TYPE_ALIASES[stem]

    for keyword, publication_type in TYPE_KEYWORD_RULES:
        if keyword in normalized:
            return publication_type

    # A bare "Abstract" carries a form but no genre.
    if record_form == "abstract":
        return "abstract"
    return "unknown"


def _normalize_type_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip().lower()
    if not text or text == "nan":
        return ""
    text = SEPARATOR_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def standardize_journal_name(value: Any) -> str | None:
    """Tidy a venue name without changing which venue it refers to."""

    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return None
    text = WHITESPACE_RE.sub(" ", text)
    text = text.strip(" \t\"'.,;")
    return text or None


def strip_trailing_parenthetical(value: str) -> str:
    """Remove a trailing publisher qualifier, e.g. "arXiv (Cornell University)".

    Only publisher and organisation qualifiers are removed. A parenthetical that
    names a series or subject is part of the venue's identity and is kept:
    "Ceylon Journal of Science (Biological Sciences)" is not the same venue as
    "Ceylon Journal of Science".

    Used only to test whether a shorter spelling of the same venue already
    exists in the corpus; the shortened form is never adopted on its own.
    """

    match = TRAILING_PARENTHETICAL_RE.search(value)
    if not match:
        return value

    inner = match.group(1).strip()
    stripped = value[: match.start()].strip()
    if not inner or not stripped:
        return value

    # A qualifier that merely repeats the venue name carries no information.
    if inner.casefold() == stripped.casefold():
        return stripped
    if any(marker in inner.casefold() for marker in ORGANISATION_MARKERS):
        return stripped
    return value


def classify_venue(name: Any, *, has_issn: bool = False) -> str:
    """Classify a venue as a journal or as the platform it actually is.

    Preprint servers, data repositories and aggregators routinely appear in the
    journal field. Counting them as journals inflates venue statistics, so they
    are labelled rather than silently treated as journals.
    """

    text = standardize_journal_name(name)
    if not text:
        return "unknown"

    lowered = text.lower()
    for keywords, venue_type in VENUE_TYPE_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return venue_type

    if has_issn or any(hint in lowered for hint in JOURNAL_NAME_HINTS):
        return "journal"
    return "other_venue"
