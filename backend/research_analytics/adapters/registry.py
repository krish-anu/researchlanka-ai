"""Source adapter registration and construction."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Type

from research_analytics.adapters.base import SourceAdapter
from research_analytics.config import FrameworkConfig, SourceConfig

SOURCE_REGISTRY: dict[str, Type[SourceAdapter]] = {}
_BUILTINS_REGISTERED = False


def register_source(source_type: str):
    """Register a source adapter class under a stable source type."""

    def decorator(adapter_class: Type[SourceAdapter]) -> Type[SourceAdapter]:
        SOURCE_REGISTRY[source_type] = adapter_class
        return adapter_class

    return decorator


def get_source_adapter(source_type: str) -> Type[SourceAdapter]:
    register_builtin_adapters()
    if source_type not in SOURCE_REGISTRY:
        discover_plugins()
    try:
        return SOURCE_REGISTRY[source_type]
    except KeyError as exc:
        raise KeyError(f"No source adapter registered for type={source_type!r}") from exc


def build_adapter_from_config(config: FrameworkConfig) -> SourceAdapter:
    """Create a source adapter from source/input configuration."""

    source = _effective_source(config)
    source_type = source.type or source.adapter or source.format
    if not source_type:
        raise ValueError("Configuration requires source.type or input.format.")

    adapter_class = get_source_adapter(source_type)
    common_kwargs = {
        "column_mapping": config.column_mapping,
        "transformations": config.transformations,
        "source_name": source.name or config.input.source_name,
        "required_fields": config.validation.required,
        "require_any_fields": config.validation.require_any,
        "adapter_version": source.adapter_version,
        "mapping_version": source.mapping_version,
    }

    if source_type == "csv":
        return adapter_class(
            source.path,
            delimiter=source.delimiter,
            encoding=source.encoding,
            **common_kwargs,
        )
    if source_type in {"json", "jsonl", "ndjson"}:
        return adapter_class(source.path, encoding=source.encoding, **common_kwargs)
    if source_type in {"excel", "xlsx", "xls"}:
        return adapter_class(
            source.path,
            sheet_name=source.sheet_name,
            header_row=source.header_row,
            **common_kwargs,
        )
    if source_type == "xml":
        return adapter_class(
            source.path,
            record_path=source.response.get("records_path", "record"),
            encoding=source.encoding,
            **common_kwargs,
        )
    if source_type == "api":
        return adapter_class(
            base_url=source.base_url,
            method=source.method,
            headers=source.headers,
            authentication=source.authentication,
            pagination=source.pagination,
            response=source.response,
            **common_kwargs,
        )
    if source_type == "oai_pmh":
        return adapter_class(
            endpoint=source.base_url or source.endpoint or source.path,
            source_name=source.name or "oai_pmh",
            max_records=source.options.get("max_records"),
        )
    if source_type == "openalex":
        return adapter_class(
            country_code=config.project.country_code,
            start_year=config.collection.start_year,
            end_year=config.collection.end_year,
            email=source.options.get("email"),
            api_key=source.options.get("api_key"),
            per_page=config.collection.batch_size,
            max_records=source.options.get("max_records"),
            strict_country_only=source.options.get("strict_country_only", False),
            retry_limit=config.collection.retry_limit,
            retry_backoff_seconds=config.collection.request_delay_seconds,
            **common_kwargs,
        )
    if source_type == "crossref":
        return adapter_class(
            affiliation_query=source.options.get("affiliation_query", ""),
            email=source.options.get("email"),
            filters=source.options.get("filters"),
            max_records=source.options.get("max_records"),
            require_first_author_lk=source.options.get("require_first_author_lk", True),
        )

    return adapter_class(**source.options)


def register_builtin_adapters() -> None:
    """Register built-in adapters lazily to avoid import cycles."""

    global _BUILTINS_REGISTERED
    if _BUILTINS_REGISTERED:
        return

    from research_analytics.adapters.api import APIAdapter
    from research_analytics.adapters.crossref import CrossrefAdapter
    from research_analytics.adapters.local_file import CSVAdapter, ExcelAdapter, JSONAdapter, XMLAdapter
    from research_analytics.adapters.oai_pmh import OAIPMHAdapter
    from research_analytics.adapters.openalex import OpenAlexAdapter

    SOURCE_REGISTRY.update(
        {
            "csv": CSVAdapter,
            "excel": ExcelAdapter,
            "xlsx": ExcelAdapter,
            "xls": ExcelAdapter,
            "json": JSONAdapter,
            "jsonl": JSONAdapter,
            "ndjson": JSONAdapter,
            "xml": XMLAdapter,
            "api": APIAdapter,
            "rest_api": APIAdapter,
            "oai_pmh": OAIPMHAdapter,
            "openalex": OpenAlexAdapter,
            "crossref": CrossrefAdapter,
        }
    )
    _BUILTINS_REGISTERED = True


def discover_plugins(plugin_dir: str | Path = "plugins") -> None:
    """Import plugin adapter modules so their register_source decorators run."""

    plugin_dir = Path(plugin_dir)
    if not plugin_dir.exists():
        return
    for adapter_path in plugin_dir.glob("*/adapter.py"):
        module_name = f"research_analytics_plugin_{adapter_path.parent.name}"
        spec = importlib.util.spec_from_file_location(module_name, adapter_path)
        if spec is None or spec.loader is None:
            continue
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)


def _effective_source(config: FrameworkConfig) -> SourceConfig:
    if config.source.type or config.source.path or config.source.base_url:
        return config.source
    return SourceConfig(
        name=config.input.source_name,
        type=config.input.format,
        path=config.input.path,
        format=config.input.format,
    )
