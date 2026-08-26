"""Compatibility exports for the publication API service."""

from src.api.core.errors import APIError
from src.api.services.publications import ResearchLankaAPI

__all__ = ["APIError", "ResearchLankaAPI"]

