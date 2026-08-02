"""Reusable research publication analytics framework."""

from research_analytics.config import FrameworkConfig, load_config
from research_analytics.adapters.registry import SOURCE_REGISTRY, register_source
from research_analytics.pipeline import ResearchPipeline
from research_analytics.schema import STANDARD_PUBLICATION_FIELDS, map_to_standard_schema

__all__ = [
    "FrameworkConfig",
    "ResearchPipeline",
    "SOURCE_REGISTRY",
    "STANDARD_PUBLICATION_FIELDS",
    "load_config",
    "map_to_standard_schema",
    "register_source",
]
