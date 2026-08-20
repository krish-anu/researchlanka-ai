"""Compatibility exports for the FastAPI model-serving app."""

from src.api.transport.fastapi_app import (
    PublicationBatchPredictionRequest,
    PublicationPredictionRequest,
    app,
    build_parser,
    create_app,
    create_model_router,
    main,
)

__all__ = [
    "PublicationBatchPredictionRequest",
    "PublicationPredictionRequest",
    "app",
    "build_parser",
    "create_app",
    "create_model_router",
    "main",
]


if __name__ == "__main__":
    main()
