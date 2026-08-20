"""FastAPI app exposing the ResearchLanka API."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from fastapi import APIRouter, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.api.core.constants import API_PREFIX, API_VERSION
from src.api.core.errors import APIError
from src.api.core.serializers import normalize_value
from src.api.repositories.postgres import PostgresPublicationRepository
from src.api.schemas import PublicationBatchPredictionRequest, PublicationPredictionRequest
from src.api.services.model_serving import PublicationClassifierService
from src.api.services.publications import ResearchLankaAPI


def query_dict(request: Request) -> dict[str, list[str]]:
    """Return query params in the format expected by the service layer."""

    query: dict[str, list[str]] = {}
    for key, value in request.query_params.multi_items():
        query.setdefault(key, []).append(value)
    return query


def bytes_payload(payload: tuple[bytes, str]) -> Response:
    body, content_type = payload
    return Response(content=body, media_type=content_type)


def error_payload(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return normalize_value(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            }
        }
    )


def create_publication_router(
    publication_service: ResearchLankaAPI | None = None,
) -> APIRouter:
    """Create the read-only publication and analytics endpoints router."""

    service = publication_service or ResearchLankaAPI(PostgresPublicationRepository())
    router = APIRouter(prefix=API_PREFIX, tags=["publications"])

    @router.get("/meta")
    async def metadata() -> dict[str, Any]:
        return service.metadata()

    @router.get("/schema/publications")
    async def publication_schema() -> dict[str, Any]:
        return service.schema()

    @router.get("/limitations")
    async def limitations() -> dict[str, Any]:
        return service.limitations()

    @router.get("/publications")
    async def list_publications(request: Request) -> dict[str, Any]:
        return service.list_publications(query_dict(request))

    @router.get("/publications/{publication_key:path}/references")
    async def publication_references(publication_key: str, request: Request) -> dict[str, Any]:
        return service.publication_references(publication_key, query_dict(request))

    @router.get("/publications/{publication_key:path}/count-audit")
    async def publication_count_audit(publication_key: str) -> dict[str, Any]:
        return service.publication_count_audit(publication_key)

    @router.get("/publications/{publication_key:path}/related")
    async def related_publications(publication_key: str, request: Request) -> dict[str, Any]:
        return service.related_publications(publication_key, query_dict(request))

    @router.get("/publications/{publication_key:path}/similar")
    async def similar_publications(publication_key: str, request: Request) -> dict[str, Any]:
        return service.similar_publications(publication_key, query_dict(request))

    @router.get("/publications/{publication_key:path}/raw")
    async def publication_raw(publication_key: str) -> dict[str, Any]:
        return service.publication_raw(publication_key)

    @router.get("/publications/{publication_key:path}")
    async def publication_detail(publication_key: str) -> dict[str, Any]:
        return service.publication_detail(publication_key)

    @router.get("/search/suggest")
    async def suggestions(request: Request) -> dict[str, Any]:
        return service.suggestions(query_dict(request))

    @router.get("/search/semantic")
    async def semantic_search(request: Request) -> dict[str, Any]:
        return service.semantic_search(query_dict(request))

    @router.get("/search/similarity")
    @router.get("/search/similar")
    async def similarity_search(request: Request) -> dict[str, Any]:
        return service.similarity_search(query_dict(request))

    @router.get("/search/facets")
    async def facets(request: Request) -> dict[str, Any]:
        return service.facets(query_dict(request))

    @router.get("/researchers")
    async def researchers(request: Request) -> dict[str, Any]:
        return service.researchers(query_dict(request))

    @router.get("/researchers/{researcher_key:path}/publications")
    async def researcher_publications(researcher_key: str, request: Request) -> dict[str, Any]:
        return service.researcher_publications(researcher_key, query_dict(request))

    @router.get("/researchers/{researcher_key:path}/coauthors")
    async def researcher_coauthors(researcher_key: str, request: Request) -> dict[str, Any]:
        return service.researcher_coauthors(researcher_key, query_dict(request))

    @router.get("/researchers/{researcher_key:path}")
    async def researcher_profile(researcher_key: str) -> dict[str, Any]:
        return service.researcher_profile(researcher_key)

    @router.get("/institutions")
    async def institutions(request: Request) -> dict[str, Any]:
        return service.institutions(query_dict(request))

    @router.get("/institutions/compare")
    async def compare_institutions(request: Request) -> dict[str, Any]:
        return service.compare_institutions(query_dict(request))

    @router.get("/institutions/{institution_key:path}/publications")
    async def institution_publications(institution_key: str, request: Request) -> dict[str, Any]:
        return service.institution_publications(institution_key, query_dict(request))

    @router.get("/institutions/{institution_key:path}/collaborators")
    async def institution_collaborators(institution_key: str, request: Request) -> dict[str, Any]:
        return service.institution_collaborators(institution_key, query_dict(request))

    @router.get("/institutions/{institution_key:path}")
    async def institution_profile(institution_key: str) -> dict[str, Any]:
        return service.institution_profile(institution_key)

    @router.get("/topics")
    async def topics(request: Request) -> dict[str, Any]:
        return service.topics(query_dict(request))

    @router.get("/topics/{topic_key:path}/publications")
    async def topic_publications(topic_key: str, request: Request) -> dict[str, Any]:
        return service.topic_publications(topic_key, query_dict(request))

    @router.get("/fields")
    async def fields(request: Request) -> dict[str, Any]:
        return service.fields(query_dict(request))

    @router.get("/analytics/overview")
    async def analytics_overview(request: Request) -> dict[str, Any]:
        return service.analytics_overview(query_dict(request))

    @router.get("/analytics/trends")
    async def analytics_trends(request: Request) -> dict[str, Any]:
        return service.analytics_trends(query_dict(request))

    @router.get("/analytics/institutions")
    async def analytics_institutions(request: Request) -> dict[str, Any]:
        return service.analytics_rankings(query_dict(request), dimension="institutions")

    @router.get("/analytics/fields")
    async def analytics_fields(request: Request) -> dict[str, Any]:
        return service.analytics_rankings(query_dict(request), dimension="primary_field")

    @router.get("/analytics/collaboration-network")
    async def collaboration_network(request: Request) -> dict[str, Any]:
        return service.collaboration_network(query_dict(request))

    @router.get("/analytics/data-quality")
    async def data_quality(request: Request) -> dict[str, Any]:
        return service.data_quality(query_dict(request))

    @router.get("/exports/publications.csv")
    async def export_publications_csv(request: Request) -> Response:
        return bytes_payload(service.export_publications(query_dict(request), file_format="csv"))

    @router.get("/exports/publications.jsonl")
    async def export_publications_jsonl(request: Request) -> Response:
        return bytes_payload(service.export_publications(query_dict(request), file_format="jsonl"))

    @router.get("/exports/analytics/{name}.csv")
    async def export_analytics_csv(name: str, request: Request) -> Response:
        return bytes_payload(service.export_analytics(query_dict(request), name=name))

    return router


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


def create_app(
    model_service: PublicationClassifierService | None = None,
    publication_service: ResearchLankaAPI | None = None,
) -> FastAPI:
    """Build the FastAPI app."""

    publication_api = publication_service or ResearchLankaAPI(PostgresPublicationRepository())
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
            content=error_payload(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=error_payload(
                "invalid_request",
                "Request validation failed.",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        message = "Endpoint not found." if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(code, message),
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=error_payload(
                "internal_error",
                "An unexpected error occurred.",
                {"error": str(exc)},
            ),
        )

    @app.get("/health")
    @app.get(f"{API_PREFIX}/health")
    async def health() -> dict[str, Any]:
        return publication_api.health()

    app.include_router(create_publication_router(publication_api))
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

    uvicorn.run("src.api.transport.fastapi_app:app", host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()
