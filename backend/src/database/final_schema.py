"""Final publication dataset schema shared by migrations and loaders."""

from __future__ import annotations

from src.pipeline.build_final_common_dataset import FINAL_MAIN_COLUMNS


FINAL_PUBLICATION_TABLE = "final_publications"
AI_CLASSIFICATION_COLUMNS = (
    "ai_classification_label",
    "ai_classification_confidence",
    "ai_classification_model",
    "ai_classification_reason",
)
FINAL_PUBLICATION_COLUMNS = tuple(FINAL_MAIN_COLUMNS)
DATABASE_PUBLICATION_COLUMNS = (
    *FINAL_PUBLICATION_COLUMNS,
    *AI_CLASSIFICATION_COLUMNS,
)

INTEGER_COLUMNS = {
    "publication_year",
    "author_count",
    "citation_count",
    "reference_count",
    "citation_count_difference_oa_minus_crossref",
    "reference_count_difference_oa_minus_crossref",
}

BOOLEAN_COLUMNS = {
    "is_oa",
    "citation_count_divergence_flag",
    "reference_count_divergence_flag",
}

DATE_COLUMNS = {
    "publication_date",
}

TIMESTAMPTZ_COLUMNS = {
    "source_datestamp",
}

TEXT_COLUMNS = set(DATABASE_PUBLICATION_COLUMNS) - (
    INTEGER_COLUMNS | BOOLEAN_COLUMNS | DATE_COLUMNS | TIMESTAMPTZ_COLUMNS
)
