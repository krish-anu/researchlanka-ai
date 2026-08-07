"""Prediction endpoint request schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PublicationPredictionRequest(BaseModel):
    """Request body for single publication classifier predictions."""

    model_config = ConfigDict(extra="allow")

    text: str | None = Field(default=None, description="Already-combined publication text.")
    title: str | None = Field(default=None, description="Publication title.")
    abstract: str | None = Field(default=None, description="Publication abstract.")
    keywords: str | list[str] | None = Field(default=None, description="Publication keywords.")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Caller metadata to echo.")


class PublicationBatchPredictionRequest(BaseModel):
    """Request body for batch publication classifier predictions."""

    records: list[PublicationPredictionRequest] = Field(min_length=1)

