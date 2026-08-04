"""Source adapters for configurable data collection and import."""

from research_analytics.adapters.api import APIAdapter
from research_analytics.adapters.base import SourceAdapter
from research_analytics.adapters.crossref import CrossrefAdapter
from research_analytics.adapters.local_file import CSVAdapter, ExcelAdapter, JSONAdapter, XMLAdapter
from research_analytics.adapters.openalex import OpenAlexAdapter
from research_analytics.adapters.oai_pmh import OAIPMHAdapter
from research_analytics.adapters.registry import SOURCE_REGISTRY, register_source

__all__ = [
    "APIAdapter",
    "CSVAdapter",
    "CrossrefAdapter",
    "ExcelAdapter",
    "JSONAdapter",
    "OAIPMHAdapter",
    "OpenAlexAdapter",
    "SOURCE_REGISTRY",
    "SourceAdapter",
    "XMLAdapter",
    "register_source",
]
