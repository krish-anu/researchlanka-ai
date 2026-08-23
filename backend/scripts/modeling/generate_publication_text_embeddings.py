#!/usr/bin/env python3
"""Generate dense publication-text embeddings.

Run from the backend folder:

    python scripts/modeling/generate_publication_text_embeddings.py

Reusable embedding logic lives in ``src.modeling.embeddings``.
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.modeling.embeddings import (  # noqa: E402
    DEFAULT_EMBEDDING_DIM,
    DEFAULT_MANIFEST_OUTPUT_PATH,
    DEFAULT_MODEL_FAMILY,
    DEFAULT_MODEL_OUTPUT_PATH,
    DEFAULT_OUTPUT_PATH,
    DEFAULT_SUMMARY_OUTPUT_PATH,
    EmbeddingResult,
    PublicationEmbeddingConfig,
    generate_publication_text_embeddings,
    main,
    result_summary,
)

__all__ = [
    "DEFAULT_EMBEDDING_DIM",
    "DEFAULT_MANIFEST_OUTPUT_PATH",
    "DEFAULT_MODEL_FAMILY",
    "DEFAULT_MODEL_OUTPUT_PATH",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_SUMMARY_OUTPUT_PATH",
    "EmbeddingResult",
    "PublicationEmbeddingConfig",
    "generate_publication_text_embeddings",
    "main",
    "result_summary",
]


if __name__ == "__main__":
    main()
