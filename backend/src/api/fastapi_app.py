"""Compatibility exports for the FastAPI app."""

from src.api.transport.fastapi_app import (
    PublicationBatchPredictionRequest,
    PublicationPredictionRequest,
    app,
    build_parser,
    create_app,
    create_model_router,
    create_publication_router,
    main,
)

__all__ = [
    "PublicationBatchPredictionRequest",
    "PublicationPredictionRequest",
    "app",
    "build_parser",
    "create_app",
    "create_model_router",
    "create_publication_router",
    "main",
]


if __name__ == "__main__":
    main()
