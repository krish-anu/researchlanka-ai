"""
Text cleaning for the ResearchLanka NMF pipeline.

Two problems showed up in the k=10 baseline sweep:

  1. Topic 8 was pure Tamil-script tokens (கக, கள, தத, ...) instead of a real
     research subject - Tamil-language content leaking into an English
     TF-IDF/NMF pipeline.
  2. Topic 10 was metadata boilerplate ("abstract available", "editorial",
     "note") rather than a research topic - records whose abstract field
     holds a placeholder string instead of real text.

Dropping the affected rows was checked and rejected (~1928 rows - too large a
share of the corpus to lose). Instead this module strips the offending
tokens/phrases out of the text itself so each row keeps whatever real English
content it has, and provides an expanded stopword list for the generic
academic language that dominated Topic 1 ("study", "using", "data", ...).

Usage:
    from src.modeling.text_cleaning import clean_text_series, CUSTOM_STOP_WORDS, cleaning_report

`combined_text()` in nmf_topic_modeling.py calls clean_text_series() by
default - see its `clean=` flag to opt out and reproduce the original
(uncleaned) baseline for comparison.
"""

from __future__ import annotations

import re

import pandas as pd
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS

# --------------------------------------------------------------------------
# 1. Non-Latin script stripping (fixes Topic 8)
# --------------------------------------------------------------------------

# Unicode blocks to strip. Tamil is the one that showed up in the k=10 sweep;
# Sinhala is included defensively since this is a Sri Lankan corpus and the
# same failure mode would produce a matching garbage topic. Add more
# `(lo, hi)` ranges here if a later sweep turns up another script.
NON_LATIN_SCRIPT_RANGES = [
    (0x0B80, 0x0BFF),  # Tamil
    (0x0D80, 0x0DFF),  # Sinhala
]

_NON_LATIN_PATTERN = re.compile(
    "["
    + "".join(f"\\u{lo:04x}-\\u{hi:04x}" for lo, hi in NON_LATIN_SCRIPT_RANGES)
    + "]+"
)


def strip_non_latin(text: str) -> str:
    """Removes Tamil/Sinhala-script runs, leaving any English content in the
    same row intact (a row with a mostly-English abstract and a Tamil title
    keeps the abstract)."""
    if not text:
        return text
    return _NON_LATIN_PATTERN.sub(" ", text)


def non_latin_char_ratio(text: str) -> float:
    """Share of characters in `text` that fall in a stripped script. Useful
    for auditing which rows are affected without dropping anything."""
    if not text:
        return 0.0
    non_latin_chars = sum(len(run) for run in _NON_LATIN_PATTERN.findall(text))
    return non_latin_chars / len(text)


# --------------------------------------------------------------------------
# 2. Metadata boilerplate stripping (fixes Topic 10)
# --------------------------------------------------------------------------

# Literal placeholder / non-research-content phrases that dominated Topic 10.
# These come from records where the real abstract wasn't captured (editorials,
# case notes, author replies) and a placeholder string sits in the
# abstract/title field instead. Check `df['abstract'].str.contains(...)` and,
# if you have a `type`/`item_type` column, prefer filtering by that instead -
# it's more principled than phrase-stripping. This list is the fallback for
# when there's no such column to filter on.
BOILERPLATE_PHRASES = [
    "abstract not available",
    "abstract available",
    "no abstract available",
    "editorial note",
    "editorial abstract",
    "editorial",
    "case report",
    "author reply",
]

_BOILERPLATE_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(p) for p in BOILERPLATE_PHRASES) + r")\b",
    flags=re.IGNORECASE,
)


def strip_boilerplate(text: str) -> str:
    if not text:
        return text
    return _BOILERPLATE_PATTERN.sub(" ", text)


def boilerplate_hit_count(texts: pd.Series) -> int:
    """How many rows contain at least one boilerplate phrase - check this
    before cleaning. If it's a large share of the corpus, a `type`-column
    filter is probably a better fix than phrase-stripping."""
    return int(texts.fillna("").str.contains(_BOILERPLATE_PATTERN, regex=True).sum())


# --------------------------------------------------------------------------
# 3. Domain stopwords (fixes Topic 1 - generic academic language)
# --------------------------------------------------------------------------

DOMAIN_STOPWORDS = {
    "study",
    "studies",
    "using",
    "used",
    "use",
    "data",
    "results",
    "result",
    "based",
    "significant",
    "analysis",
    "research",
    "factors",
    "factor",
    "findings",
    "finding",
    "methods",
    "method",
    "model",
    "models",
    "high",
    "paper",
    "article",
    "approach",
    "propose",
    "proposed",
    "present",
    "presents",
    "available",
    "sri",
    "lanka",
    "srilanka",
    "lankan",
    "south",
    "asia",
    "asian",
    "universtiy",
    "conference",
    "international_conference",
    "international",
    "text",
    "pre",
    "proceedings",
    "conference_proceedings",
    "2023",
    "2024",
    "moratuwa",
    "moratuwa engineering conference",
    "moratuwa engineering",
    "pre text",
    "19",
    "review",
    "sri lankan",
    "development",
    "design",
    "conduct",
    "conducted",
    "different"
    # leftover after boilerplate phrase-stripping (e.g. "editorial abstract" -> "available")
}

# sklearn's TfidfVectorizer(stop_words=...) accepts a list; sorted for a
# stable, diffable order.
CUSTOM_STOP_WORDS = sorted(ENGLISH_STOP_WORDS | DOMAIN_STOPWORDS)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def clean_text_series(texts: pd.Series) -> pd.Series:
    """Non-Latin stripping + boilerplate stripping + whitespace collapse.

    Stopwords are deliberately NOT applied here - they're passed to
    TfidfVectorizer(stop_words=CUSTOM_STOP_WORDS) instead, since sklearn's
    tokenizer-aware removal (word-boundary matching, n-gram interaction)
    behaves better than a manual regex pass would.
    """
    cleaned = texts.fillna("").astype(str)
    cleaned = cleaned.apply(strip_non_latin)
    cleaned = cleaned.apply(strip_boilerplate)
    cleaned = cleaned.str.replace(r"\s+", " ", regex=True).str.strip()
    return cleaned


def cleaning_report(texts: pd.Series) -> dict:
    """Before-cleaning stats to record alongside the model artifacts, so the
    cleaning step is documented rather than silent in the writeup."""
    raw = texts.fillna("").astype(str)
    non_latin_hits = raw.apply(lambda t: non_latin_char_ratio(t) > 0.0).sum()
    boilerplate_hits = boilerplate_hit_count(raw)
    return {
        "n_rows": int(len(raw)),
        "rows_with_non_latin_chars": int(non_latin_hits),
        "rows_with_boilerplate_phrases": int(boilerplate_hits),
    }
