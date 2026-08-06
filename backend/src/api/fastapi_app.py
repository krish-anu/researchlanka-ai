"""FastAPI app exposing model-serving endpoints."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from src.api.constants import API_PREFIX, API_VERSION, DATASET_STAGE
from src.api.errors import APIError
from src.api.model_service import PublicationClassifierService
from src.api.serializers import normalize_value


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


def create_model_router(
    model_service: PublicationClassifierService | None = None,
) -> APIRouter:
    """Create the model endpoints router."""

    service = model_service or PublicationClassifierService()
    router = APIRouter(prefix=f"{API_PREFIX}/models", tags=["models"])

    @router.get("")
    async def list_models() -> dict[str, Any]:
        return service.list_models()

    @router.get("/{model_id}")
    async def model_detail(model_id: str) -> dict[str, Any]:
        return service.model_detail(model_id)

    @router.post("/{model_id}/predict")
    async def predict_one(model_id: str, request: PublicationPredictionRequest) -> dict[str, Any]:
        return service.predict_one(model_id, request.model_dump(exclude_none=True))

    @router.post("/{model_id}/predict-batch")
    async def predict_batch(model_id: str, request: PublicationBatchPredictionRequest) -> dict[str, Any]:
        return service.predict_batch(
            model_id,
            [record.model_dump(exclude_none=True) for record in request.records],
        )

    return router


def create_app(model_service: PublicationClassifierService | None = None) -> FastAPI:
    """Build the FastAPI app."""

    app = FastAPI(
        title="ResearchLanka API",
        version=API_VERSION,
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=f"{API_PREFIX}/redoc",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(APIError)
    async def api_error_handler(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status,
            content=normalize_value(
                {
                    "error": {
                        "code": exc.code,
                        "message": exc.message,
                        "details": exc.details,
                    }
                }
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=normalize_value(
                {
                    "error": {
                        "code": "invalid_request",
                        "message": "Request validation failed.",
                        "details": {"errors": exc.errors()},
                    }
                }
            ),
        )

    @app.get("/health")
    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict[str, Any]:
        return {
            "data": {"status": "ok", "api_version": API_VERSION},
            "meta": {"api_version": API_VERSION, "dataset_stage": DATASET_STAGE},
        }

    app.include_router(create_model_router(model_service))
    return app


app = create_app()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Serve the ResearchLanka FastAPI model API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--reload", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    import uvicorn

    uvicorn.run("src.api.fastapi_app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
