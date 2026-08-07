#!/usr/bin/env python3
"""Build compact TF-IDF feature rows for publication text.

Run from the backend folder:

    python scripts/extraction/build_publication_tfidf_features.py

The output keeps one row per publication with usable text and writes a compact
semicolon-delimited feature vector plus a separate vocabulary/IDF file.
"""

from __future__ import annotations

import argparse
import csv
import html
import math
import re
import sys
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = PROJECT_ROOT / "data" / "processed" / "common" / "common_publications_final.csv"
DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "publication_tfidf_features_all_years.csv"
)
DEFAULT_VOCABULARY_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "publication_tfidf_vocabulary_all_years.csv"
)
DEFAULT_SUMMARY_OUTPUT = (
    PROJECT_ROOT
    / "data"
    / "processed"
    / "common"
    / "publication_tfidf_summary_all_years.csv"
)

DEFAULT_TEXT_COLUMNS = ["title", "abstract", "keywords"]
DEFAULT_MAX_FEATURES = 5_000
DEFAULT_MIN_DF = 2
DEFAULT_MAX_DF = 0.95
DEFAULT_NGRAM_MAX = 2
DEFAULT_TOP_FEATURES_PER_RECORD = 50

METADATA_FIELDS = [
    "record_number",
    "publication_year",
    "title",
    "doi",
    "openalex_id",
    "source_dataset",
    "source_institution_id",
    "source_record_id",
]
FEATURE_FIELDS = [
    *METADATA_FIELDS,
    "token_count",
    "tfidf_feature_count",
    "tfidf_features",
]
VOCABULARY_FIELDS = [
    "vocabulary_index",
    "term",
    "document_frequency",
    "term_frequency",
    "idf",
]

HTML_TAG_RE = re.compile(r"<[^>]+>")
PUNCTUATION_RE = re.compile(r"[^\w\s]")
TOKEN_RE = re.compile(r"[a-z0-9]+")
WHITESPACE_RE = re.compile(r"\s+")

DEFAULT_STOP_WORDS = {
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can",
    "did",
    "do",
    "does",
    "doing",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "has",
    "have",
    "having",
    "he",
    "her",
    "here",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "itself",
    "just",
    "me",
    "more",
    "most",
    "my",
    "myself",
    "no",
    "nor",
    "not",
    "now",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "she",
    "should",
    "so",
    "some",
    "such",
    "than",
    "that",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "we",
    "were",
    "what",
    "when",
    "where",
    "which",
    "while",
    "who",
    "whom",
    "why",
    "with",
    "you",
    "your",
    "yours",
    "yourself",
    "yourselves",
}


@dataclass(frozen=True)
class Document:
    metadata: dict[str, str]
    term_counts: Counter[str]
    token_count: int


def set_large_csv_field_limit() -> None:
    """Allow large abstract/metadata fields in the source CSV."""
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


def clean_text(value: str | None) -> str:
    text = value or ""
    previous = None
    while previous != text:
        previous = text
        text = html.unescape(text)
    text = HTML_TAG_RE.sub(" ", text)
    return WHITESPACE_RE.sub(" ", text).strip()


def normalize_text(value: str | None) -> str:
    text = clean_text(value)
    normalized = unicodedata.normalize("NFKD", text)
    normalized = "".join(char for char in normalized if not unicodedata.combining(char))
    normalized = normalized.casefold()
    normalized = PUNCTUATION_RE.sub(" ", normalized)
    return WHITESPACE_RE.sub(" ", normalized).strip()


def tokenize_text(
    value: str | None,
    *,
    stop_words: set[str] | None = None,
    min_token_length: int = 2,
) -> list[str]:
    stop_words = stop_words or set()
    tokens = TOKEN_RE.findall(normalize_text(value))
    return [
        token
        for token in tokens
        if len(token) >= min_token_length and token not in stop_words
    ]


def build_ngrams(tokens: list[str], ngram_max: int) -> list[str]:
    if ngram_max < 1:
        raise ValueError("ngram_max must be at least 1")

    terms: list[str] = []
    for ngram_size in range(1, ngram_max + 1):
        if len(tokens) < ngram_size:
            break
        terms.extend(
            " ".join(tokens[index : index + ngram_size])
            for index in range(0, len(tokens) - ngram_size + 1)
        )
    return terms


def parse_text_columns(value: str) -> list[str]:
    columns = [column.strip() for column in value.split(",") if column.strip()]
    if not columns:
        raise argparse.ArgumentTypeError("at least one text column is required")
    return columns


def parse_document_frequency(value: str) -> int | float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid document frequency value: {value}") from exc

    if parsed <= 0:
        raise argparse.ArgumentTypeError("document frequency thresholds must be positive")
    if parsed < 1 or ("." in value and parsed == 1):
        return parsed
    if not parsed.is_integer():
        raise argparse.ArgumentTypeError(
            "document frequency values above 1 must be whole numbers"
        )
    return int(parsed)


def resolve_document_frequency(
    threshold: int | float,
    document_count: int,
    *,
    is_minimum: bool,
) -> int:
    if document_count <= 0:
        return 0
    if isinstance(threshold, float) and threshold <= 1:
        resolved = (
            math.ceil(document_count * threshold)
            if is_minimum
            else math.floor(document_count * threshold)
        )
    else:
        resolved = int(threshold)
    return min(max(1, resolved), document_count)


def format_float(value: float) -> str:
    return f"{value:.6f}"


def document_text(row: dict[str, str], text_columns: Iterable[str]) -> str:
    return " ".join(clean_text(row.get(column, "")) for column in text_columns)


def load_documents(
    input_path: Path,
    *,
    text_columns: list[str],
    ngram_max: int,
    keep_stop_words: bool,
    min_token_length: int,
) -> tuple[list[Document], int]:
    documents: list[Document] = []
    input_rows = 0
    stop_words = set() if keep_stop_words else DEFAULT_STOP_WORDS

    with input_path.open(newline="", encoding="utf-8") as input_file:
        reader = csv.DictReader(input_file)
        for source_index, row in enumerate(reader, start=1):
            input_rows += 1
            tokens = tokenize_text(
                document_text(row, text_columns),
                stop_words=stop_words,
                min_token_length=min_token_length,
            )
            terms = build_ngrams(tokens, ngram_max)
            if not terms:
                continue

            metadata = {
                field: str(source_index) if field == "record_number" else row.get(field, "")
                for field in METADATA_FIELDS
            }
            documents.append(
                Document(
                    metadata=metadata,
                    term_counts=Counter(terms),
                    token_count=len(tokens),
                )
            )

    return documents, input_rows


def build_vocabulary(
    documents: list[Document],
    *,
    max_features: int,
    min_df: int | float,
    max_df: int | float,
) -> tuple[dict[str, int], dict[str, int], dict[str, int], dict[str, float]]:
    document_frequency: Counter[str] = Counter()
    term_frequency: Counter[str] = Counter()
    for document in documents:
        document_frequency.update(document.term_counts.keys())
        term_frequency.update(document.term_counts)

    document_count = len(documents)
    min_df_count = resolve_document_frequency(
        min_df,
        document_count,
        is_minimum=True,
    )
    max_df_count = resolve_document_frequency(
        max_df,
        document_count,
        is_minimum=False,
    )

    candidates = [
        term
        for term, frequency in document_frequency.items()
        if min_df_count <= frequency <= max_df_count
    ]
    ranked_terms = sorted(
        candidates,
        key=lambda term: (-term_frequency[term], -document_frequency[term], term),
    )
    if max_features > 0:
        ranked_terms = ranked_terms[:max_features]

    vocabulary = {term: index for index, term in enumerate(ranked_terms)}
    idf = {
        term: math.log((1 + document_count) / (1 + document_frequency[term])) + 1
        for term in vocabulary
    }
    return vocabulary, dict(document_frequency), dict(term_frequency), idf


def vectorize_document(
    document: Document,
    *,
    vocabulary: dict[str, int],
    idf: dict[str, float],
    top_features_per_record: int,
) -> tuple[int, str]:
    weights: list[tuple[str, int, float]] = []
    for term, count in document.term_counts.items():
        vocabulary_index = vocabulary.get(term)
        if vocabulary_index is None:
            continue
        weights.append((term, vocabulary_index, count * idf[term]))

    norm = math.sqrt(sum(weight * weight for _, _, weight in weights))
    if norm:
        weights = [(term, index, weight / norm) for term, index, weight in weights]

    weights.sort(key=lambda item: (-item[2], item[0]))
    emitted_weights = weights
    if top_features_per_record > 0:
        emitted_weights = weights[:top_features_per_record]

    feature_text = "; ".join(
        f"{term}:{format_float(weight)}" for term, _, weight in emitted_weights
    )
    return len(weights), feature_text


def build_tfidf_features(
    input_path: Path,
    *,
    text_columns: list[str] | None = None,
    max_features: int = DEFAULT_MAX_FEATURES,
    min_df: int | float = DEFAULT_MIN_DF,
    max_df: int | float = DEFAULT_MAX_DF,
    ngram_max: int = DEFAULT_NGRAM_MAX,
    top_features_per_record: int = DEFAULT_TOP_FEATURES_PER_RECORD,
    keep_stop_words: bool = False,
    min_token_length: int = 2,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    text_columns = text_columns or DEFAULT_TEXT_COLUMNS
    documents, input_rows = load_documents(
        input_path,
        text_columns=text_columns,
        ngram_max=ngram_max,
        keep_stop_words=keep_stop_words,
        min_token_length=min_token_length,
    )
    vocabulary, document_frequency, term_frequency, idf = build_vocabulary(
        documents,
        max_features=max_features,
        min_df=min_df,
        max_df=max_df,
    )

    feature_rows: list[dict[str, str]] = []
    for document in documents:
        nonzero_count, features = vectorize_document(
            document,
            vocabulary=vocabulary,
            idf=idf,
            top_features_per_record=top_features_per_record,
        )
        if not features:
            continue
        feature_rows.append(
            {
                **document.metadata,
                "token_count": str(document.token_count),
                "tfidf_feature_count": str(nonzero_count),
                "tfidf_features": features,
            }
        )

    vocabulary_rows = [
        {
            "vocabulary_index": str(index),
            "term": term,
            "document_frequency": str(document_frequency[term]),
            "term_frequency": str(term_frequency[term]),
            "idf": format_float(idf[term]),
        }
        for term, index in sorted(vocabulary.items(), key=lambda item: item[1])
    ]

    summary_rows = [
        {"metric": "input_csv", "value": str(input_path)},
        {"metric": "input_rows", "value": str(input_rows)},
        {"metric": "documents_with_text", "value": str(len(documents))},
        {"metric": "documents_with_features", "value": str(len(feature_rows))},
        {"metric": "vocabulary_size", "value": str(len(vocabulary))},
        {"metric": "text_columns", "value": "; ".join(text_columns)},
        {"metric": "max_features", "value": str(max_features)},
        {"metric": "min_df", "value": str(min_df)},
        {"metric": "max_df", "value": str(max_df)},
        {"metric": "ngram_max", "value": str(ngram_max)},
        {"metric": "top_features_per_record", "value": str(top_features_per_record)},
        {"metric": "min_token_length", "value": str(min_token_length)},
        {
            "metric": "idf_formula",
            "value": "log((1 + document_count) / (1 + document_frequency)) + 1",
        },
        {"metric": "normalization", "value": "l2"},
        {"metric": "stop_words", "value": "kept" if keep_stop_words else "removed"},
    ]

    return feature_rows, vocabulary_rows, summary_rows


def write_csv(output_path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_tfidf_outputs(
    *,
    output_path: Path,
    vocabulary_output_path: Path,
    summary_output_path: Path,
    feature_rows: list[dict[str, str]],
    vocabulary_rows: list[dict[str, str]],
    summary_rows: list[dict[str, str]],
) -> None:
    write_csv(output_path, FEATURE_FIELDS, feature_rows)
    write_csv(vocabulary_output_path, VOCABULARY_FIELDS, vocabulary_rows)
    write_csv(summary_output_path, ["metric", "value"], summary_rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build compact TF-IDF features from publication title, abstract, and keyword text."
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Input publication CSV. Default: {DEFAULT_INPUT}",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output publication TF-IDF feature CSV. Default: {DEFAULT_OUTPUT}",
    )
    parser.add_argument(
        "--vocabulary-output",
        type=Path,
        default=DEFAULT_VOCABULARY_OUTPUT,
        help=f"Output vocabulary CSV. Default: {DEFAULT_VOCABULARY_OUTPUT}",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=DEFAULT_SUMMARY_OUTPUT,
        help=f"Output summary CSV. Default: {DEFAULT_SUMMARY_OUTPUT}",
    )
    parser.add_argument(
        "--text-columns",
        type=parse_text_columns,
        default=DEFAULT_TEXT_COLUMNS,
        help="Comma-separated text columns to combine. Default: title,abstract,keywords",
    )
    parser.add_argument(
        "--max-features",
        type=int,
        default=DEFAULT_MAX_FEATURES,
        help="Maximum vocabulary size. Use 0 for no cap.",
    )
    parser.add_argument(
        "--min-df",
        type=parse_document_frequency,
        default=DEFAULT_MIN_DF,
        help="Minimum document frequency as a count or proportion. Default: 2",
    )
    parser.add_argument(
        "--max-df",
        type=parse_document_frequency,
        default=DEFAULT_MAX_DF,
        help="Maximum document frequency as a count or proportion. Default: 0.95",
    )
    parser.add_argument(
        "--ngram-max",
        type=int,
        default=DEFAULT_NGRAM_MAX,
        help="Largest n-gram size to include. Default: 2",
    )
    parser.add_argument(
        "--top-features-per-record",
        type=int,
        default=DEFAULT_TOP_FEATURES_PER_RECORD,
        help="Maximum features stored per publication row. Use 0 for all non-zero features.",
    )
    parser.add_argument(
        "--keep-stop-words",
        action="store_true",
        help="Keep common English stop words instead of removing them.",
    )
    parser.add_argument(
        "--min-token-length",
        type=int,
        default=2,
        help="Minimum token length after normalization. Default: 2",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    set_large_csv_field_limit()
    feature_rows, vocabulary_rows, summary_rows = build_tfidf_features(
        args.input,
        text_columns=args.text_columns,
        max_features=args.max_features,
        min_df=args.min_df,
        max_df=args.max_df,
        ngram_max=args.ngram_max,
        top_features_per_record=args.top_features_per_record,
        keep_stop_words=args.keep_stop_words,
        min_token_length=args.min_token_length,
    )
    write_tfidf_outputs(
        output_path=args.output,
        vocabulary_output_path=args.vocabulary_output,
        summary_output_path=args.summary_output,
        feature_rows=feature_rows,
        vocabulary_rows=vocabulary_rows,
        summary_rows=summary_rows,
    )
    print(f"Wrote {len(feature_rows)} TF-IDF feature rows to {args.output}")
    print(f"Wrote {len(vocabulary_rows)} vocabulary rows to {args.vocabulary_output}")
    print(f"Wrote summary to {args.summary_output}")


if __name__ == "__main__":
    main()
