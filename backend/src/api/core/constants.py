"""Shared constants for the ResearchLanka API."""

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100
DATASET_STAGE = "final_publications"
API_VERSION = "v1"
API_PREFIX = "/api/v1"
PUBLICATION_COVERAGE_START_YEAR = 2016
PUBLICATION_COVERAGE_END_YEAR = 2026

LIST_FILTERS = {
    "q",
    "year_min",
    "year_max",
    "type",
    "institution",
    "country",
    "field",
    "researcher",
    "subfield",
    "topic",
    "nmf_topic",
    "nmf_topic_id",
    "journal",
    "source_dataset",
    "is_oa",
    "has_doi",
    "has_abstract",
    "quality_flag",
}

SORT_OPTIONS = {"relevance", "year_desc", "year_asc", "citations_desc", "title_asc"}

ARRAY_FIELDS = {
    "authors",
    "author_orcids",
    "institutions",
    "sri_lankan_institutions",
    "countries",
    "issn",
    "concepts",
    "topics",
    "funder_name",
    "funder_doi",
    "funder_identifier",
    "funder_award",
    "source_dataset",
}

PUBLICATION_SUMMARY_FIELDS = [
    "publication_key",
    "title",
    "doi",
    "publication_year",
    "type",
    "authors",
    "institutions",
    "journal",
    "publisher",
    "citation_count",
    "reference_count",
    "is_oa",
    "oa_status",
    "primary_field",
    "primary_subfield",
    "source_dataset",
    "quality_flags",
    "nmf_topic_id",
    "nmf_topic_name",
    "nmf_topic_weight",
    "semantic_score",
    "semantic_rank",
    "similarity_score",
    "similarity_rank",
]
