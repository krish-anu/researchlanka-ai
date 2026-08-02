"""Reusable pagination strategy helpers for source adapters."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PagePagination:
    page_parameter: str = "page"
    page_size_parameter: str = "limit"
    page_size: int = 100
    start_page: int = 1

    def initial_params(self) -> dict[str, Any]:
        return {
            self.page_parameter: self.start_page,
            self.page_size_parameter: self.page_size,
        }


@dataclass(frozen=True)
class OffsetPagination:
    offset_parameter: str = "offset"
    page_size_parameter: str = "limit"
    page_size: int = 100
    start_offset: int = 0

    def initial_params(self) -> dict[str, Any]:
        return {
            self.offset_parameter: self.start_offset,
            self.page_size_parameter: self.page_size,
        }


@dataclass(frozen=True)
class CursorPagination:
    cursor_parameter: str = "cursor"
    start_cursor: str | None = None

    def initial_params(self) -> dict[str, Any]:
        return {self.cursor_parameter: self.start_cursor} if self.start_cursor else {}


@dataclass(frozen=True)
class NextLinkPagination:
    next_url_path: str

    def initial_params(self) -> dict[str, Any]:
        return {}


@dataclass(frozen=True)
class ResumptionTokenPagination:
    token_parameter: str = "resumptionToken"

    def initial_params(self) -> dict[str, Any]:
        return {}
