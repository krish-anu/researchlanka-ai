"""Configuration loading for reusable framework runs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ProjectConfig:
    name: str = "Research Analytics"
    country_name: str | None = None
    country_code: str | None = None
    dashboard_title: str | None = None


@dataclass(frozen=True)
class CollectionConfig:
    start_year: int | None = None
    end_year: int | None = None
    batch_size: int = 200
    retry_limit: int = 3
    request_delay_seconds: float = 1.0


@dataclass(frozen=True)
class PipelineStages:
    collect: bool = True
    transform: bool = True
    validate: bool = True
    clean: bool = True
    enrich: bool = False
    deduplicate: bool = True
    resolve_entities: bool = False
    load_database: bool = False
    run_analytics: bool = True
    export: bool = True
    classify: bool = False
    topic_modeling: bool = False
    semantic_search: bool = False
    forecasting: bool = False


@dataclass(frozen=True)
class InstitutionRegistryConfig:
    path: str | None = None
    country_code_column: str = "country_code"
    institution_id_column: str = "institution_id"
    preferred_name_column: str = "preferred_name"
    alternative_name_column: str = "alternative_name"
    parent_id_column: str = "parent_institution_id"
    ror_id_column: str = "ror_id"


@dataclass(frozen=True)
class CleaningConfig:
    normalize_doi: bool = True
    normalize_title: bool = True
    normalize_author_names: bool = True
    normalize_institutions: bool = True
    valid_year_minimum: int | None = None
    valid_year_maximum: int | None = None
    required_fields: tuple[str, ...] = ("title",)
    optional_fields: tuple[str, ...] = ("doi", "abstract", "keywords")


@dataclass(frozen=True)
class DeduplicationConfig:
    enabled: bool = True
    doi_match_enabled: bool = True
    doi_automatic_merge: bool = True
    exact_title_match_enabled: bool = True
    exact_title_require_same_year: bool = True
    fuzzy_title_match_enabled: bool = False
    fuzzy_title_threshold: int = 90
    minimum_matching_authors: int = 1
    maximum_year_difference: int = 1
    uncertain_matches_manual_review: bool = True


@dataclass(frozen=True)
class SourceConfig:
    name: str | None = None
    type: str | None = None
    enabled: bool = True
    path: str | None = None
    format: str | None = None
    delimiter: str = ","
    encoding: str = "utf-8"
    sheet_name: str | int | None = None
    header_row: int = 0
    base_url: str | None = None
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    authentication: dict[str, Any] = field(default_factory=dict)
    pagination: dict[str, Any] = field(default_factory=dict)
    response: dict[str, Any] = field(default_factory=dict)
    adapter_version: str = "1.0"
    mapping_version: str = "1.0"
    plugin: str | None = None
    options: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationRules:
    required: tuple[str, ...] = ("title",)
    require_any: tuple[str, ...] = ("doi", "authors", "publication_year", "source_record_id")


@dataclass(frozen=True)
class InputConfig:
    path: str | None = None
    format: str | None = None
    source_name: str = "user_dataset"


@dataclass(frozen=True)
class ExportConfig:
    output_dir: str = "outputs"
    formats: tuple[str, ...] = ("csv", "json")


@dataclass(frozen=True)
class FrameworkConfig:
    project: ProjectConfig = field(default_factory=ProjectConfig)
    input: InputConfig = field(default_factory=InputConfig)
    collection: CollectionConfig = field(default_factory=CollectionConfig)
    pipeline: PipelineStages = field(default_factory=PipelineStages)
    cleaning: CleaningConfig = field(default_factory=CleaningConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)
    export: ExportConfig = field(default_factory=ExportConfig)
    institution_registry: InstitutionRegistryConfig = field(default_factory=InstitutionRegistryConfig)
    source: SourceConfig = field(default_factory=SourceConfig)
    validation: ValidationRules = field(default_factory=ValidationRules)
    column_mapping: dict[str, str] = field(default_factory=dict)
    transformations: dict[str, dict[str, Any]] = field(default_factory=dict)
    sources: dict[str, Any] = field(default_factory=dict)
    aliases: dict[str, str] = field(default_factory=dict)
    categories: list[str] = field(default_factory=list)
    analytics: dict[str, bool] = field(default_factory=dict)
    machine_learning: dict[str, Any] = field(default_factory=dict)
    publication_types: tuple[str, ...] = field(default_factory=tuple)


def load_config(path: str | Path) -> FrameworkConfig:
    """Load a JSON config, or YAML when PyYAML is installed."""

    path = Path(path)
    data = _load_mapping(path)
    return config_from_dict(data)


def config_from_dict(data: dict[str, Any]) -> FrameworkConfig:
    """Create a typed framework config from a plain mapping."""

    cleaning = data.get("cleaning", {})
    valid_year = cleaning.get("valid_year", {}) if isinstance(cleaning, dict) else {}
    deduplication = data.get("deduplication", {})
    doi_match = deduplication.get("doi_match", {}) if isinstance(deduplication, dict) else {}
    exact_title = (
        deduplication.get("exact_title_match", {}) if isinstance(deduplication, dict) else {}
    )
    fuzzy_title = (
        deduplication.get("fuzzy_title_match", {}) if isinstance(deduplication, dict) else {}
    )
    author_match = (
        deduplication.get("author_match", {}) if isinstance(deduplication, dict) else {}
    )
    year_difference = (
        deduplication.get("year_difference", {}) if isinstance(deduplication, dict) else {}
    )
    uncertain = (
        deduplication.get("uncertain_matches", {}) if isinstance(deduplication, dict) else {}
    )
    validation = data.get("validation", {})

    country = data.get("country", {})
    project = data.get("project", {})
    project_data = {
        **project,
        **(
            {
                "country_name": country.get("name"),
                "country_code": country.get("code"),
            }
            if country
            else {}
        ),
    }
    coverage = data.get("coverage", {})
    collection_data = {
        **data.get("collection", {}),
        **(
            {
                "start_year": coverage.get("start_year"),
                "end_year": coverage.get("end_year"),
            }
            if coverage
            else {}
        ),
    }

    return FrameworkConfig(
        project=ProjectConfig(**project_data),
        input=InputConfig(**data.get("input", {})),
        collection=CollectionConfig(**collection_data),
        pipeline=PipelineStages(**data.get("pipeline", {})),
        cleaning=CleaningConfig(
            normalize_doi=cleaning.get("normalize_doi", True),
            normalize_title=cleaning.get("normalize_title", True),
            normalize_author_names=cleaning.get("normalize_author_names", True),
            normalize_institutions=cleaning.get("normalize_institutions", True),
            valid_year_minimum=valid_year.get("minimum"),
            valid_year_maximum=valid_year.get("maximum"),
            required_fields=tuple(cleaning.get("required_fields", ("title",))),
            optional_fields=tuple(cleaning.get("optional_fields", ("doi", "abstract", "keywords"))),
        ),
        deduplication=DeduplicationConfig(
            enabled=deduplication.get("enabled", True),
            doi_match_enabled=doi_match.get("enabled", True),
            doi_automatic_merge=doi_match.get("automatic_merge", True),
            exact_title_match_enabled=exact_title.get("enabled", True),
            exact_title_require_same_year=exact_title.get("require_same_year", True),
            fuzzy_title_match_enabled=fuzzy_title.get("enabled", False),
            fuzzy_title_threshold=fuzzy_title.get("threshold", 90),
            minimum_matching_authors=author_match.get("minimum_matching_authors", 1),
            maximum_year_difference=year_difference.get("maximum", 1),
            uncertain_matches_manual_review=uncertain.get("send_to_manual_review", True),
        ),
        export=ExportConfig(
            output_dir=data.get("export", {}).get("output_dir", "outputs"),
            formats=tuple(data.get("export", {}).get("formats", ("csv", "json"))),
        ),
        institution_registry=InstitutionRegistryConfig(
            **data.get("institution_registry", {})
        ),
        source=SourceConfig(**data.get("source", {})),
        validation=ValidationRules(
            required=tuple(validation.get("required", ("title",))),
            require_any=tuple(
                validation.get(
                    "require_any",
                    ("doi", "authors", "publication_year", "source_record_id"),
                )
            ),
        ),
        column_mapping=data.get("column_mapping", {}),
        transformations=data.get("transformations", {}),
        sources=data.get("sources", {}),
        aliases=data.get("aliases", {}),
        categories=data.get("categories", []),
        analytics=data.get("analytics", {}),
        machine_learning=data.get("machine_learning", {}),
        publication_types=tuple(data.get("publication_types", ())),
    )


def _load_mapping(path: Path) -> dict[str, Any]:
    if path.suffix.lower() == ".json":
        return json.loads(path.read_text(encoding="utf-8"))

    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "YAML config files require PyYAML. Install it or provide a JSON config."
            ) from exc
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError(f"Configuration must be a mapping: {path}")
        return loaded

    raise ValueError(f"Unsupported config format: {path.suffix}. Use .json, .yaml, or .yml.")
