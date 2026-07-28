import csv
import json

from research_analytics import ResearchPipeline, load_config, map_to_standard_schema
from research_analytics.adapters import SOURCE_REGISTRY
from research_analytics.adapters.api import APIAdapter
from research_analytics.adapters.openalex import OpenAlexAdapter
from research_analytics.adapters.registry import get_source_adapter
from research_analytics.analytics import run_field_aware_analytics
from research_analytics.cli import run_stage
from research_analytics.config import config_from_dict
from research_analytics.institutions import NationalInstitutionRegistry, enrich_national_context
from research_analytics.schema import STANDARD_PUBLICATION_FIELDS


def test_standard_schema_maps_user_columns_without_country_specific_code():
    raw = {
        "paper_name": "Configurable research framework",
        "researcher": "Asha Example",
        "university": "Example University",
        "published_year": "2024",
    }
    mapped = map_to_standard_schema(
        raw,
        {
            "paper_name": "title",
            "researcher": "authors",
            "university": "institutions",
            "published_year": "publication_year",
        },
        source_name="user_upload",
    )

    assert set(STANDARD_PUBLICATION_FIELDS).issubset(mapped)
    assert mapped["title"] == "Configurable research framework"
    assert mapped["authors"] == "Asha Example"
    assert mapped["institutions"] == "Example University"
    assert mapped["publication_year"] == "2024"
    assert mapped["source_name"] == "user_upload"


def test_pipeline_runs_from_configuration_and_exports_reports(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,paper_name,researcher,university,published_year,doi,citation_count",
                "1,Same title,A. Author,Example University,2022,https://doi.org/10.1/ABC,4",
                "2,Same title,A Author,EU,2022,10.1/abc,4",
                "3,Another title,B. Author,Other University,2023,,1",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "outputs"
    config = config_from_dict(
        {
            "project": {
                "name": "Second Dataset",
                "country_name": "Example Country",
                "country_code": "EX",
            },
            "input": {
                "path": str(dataset),
                "format": "csv",
                "source_name": "external_dataset",
            },
            "column_mapping": {
                "record_id": "source_record_id",
                "paper_name": "title",
                "researcher": "authors",
                "university": "institutions",
                "published_year": "publication_year",
            },
            "cleaning": {
                "required_fields": ["title"],
                "valid_year": {"minimum": 2000, "maximum": 2030},
            },
            "export": {"output_dir": str(output_dir), "formats": ["csv", "json"]},
        }
    )

    result = ResearchPipeline(config).run_all()

    assert len(result.raw_records) == 3
    assert len(result.cleaned_records) == 3
    assert len(result.deduplicated_records) == 2
    assert result.validation_report is not None
    assert result.validation_report.duplicate_doi_count == 1
    assert (output_dir / "cleaned_publications.csv").exists()
    assert (output_dir / "deduplicated_publications.csv").exists()
    assert (output_dir / "national_publications.csv").exists()
    assert (output_dir / "authors.csv").exists()
    assert (output_dir / "institutions.csv").exists()
    assert (output_dir / "publication_author_links.csv").exists()
    assert (output_dir / "publication_institution_links.csv").exists()
    assert (output_dir / "collaboration_edges.csv").exists()
    assert (output_dir / "national_analytics_summary.json").exists()
    assert (output_dir / "automatic_matches.csv").exists()
    assert (output_dir / "data_quality_report.json").exists()
    assert (output_dir / "analytics_summary.json").exists()

    with (output_dir / "deduplicated_publications.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2


def test_project_country_is_supplied_by_config_not_pipeline_code(tmp_path):
    first = load_config("configurations/sri_lanka/config.json")
    second = load_config("configurations/example_country/config.json")

    assert first.project.country_code == "LK"
    assert second.project.country_code == "EX"
    assert first.institution_registry.path == "configurations/sri_lanka/institutions.csv"
    assert second.institution_registry.path == "configurations/example_country/institutions.csv"
    assert first.input.path == "data/processed/repositories_combined.csv"
    assert second.input.path == "examples/sample_publications.csv"


def test_country_config_shape_can_select_first_enabled_source():
    config = config_from_dict(
        {
            "country": {"name": "Malaysia", "code": "MY"},
            "coverage": {"start_year": 2020, "end_year": 2026},
            "institution_registry": "configurations/example_country/institutions.csv",
            "sources": {
                "openalex": {
                    "enabled": True,
                    "endpoint": "https://api.openalex.org/works",
                    "filter": "institutions.country_code:MY",
                    "options": {"max_records": 10},
                },
                "local_repository": {
                    "enabled": False,
                    "adapter": "oai_pmh",
                    "endpoint": "https://repo.example/oai",
                },
            },
            "dashboard": {"title": "Malaysia Research Portal"},
        }
    )

    assert config.project.country_name == "Malaysia"
    assert config.project.country_code == "MY"
    assert config.project.dashboard_title == "Malaysia Research Portal"
    assert config.collection.start_year == 2020
    assert config.source.name == "openalex"
    assert config.source.type == "openalex"
    assert config.source.base_url == "https://api.openalex.org/works"
    assert config.source.filter == "institutions.country_code:MY"
    assert config.institution_registry.path == "configurations/example_country/institutions.csv"


def test_stage_runner_executes_all_pipeline_steps_from_config():
    config = load_config("configurations/example_country/config.json")
    output = run_stage(ResearchPipeline(config), "all")

    assert output == "Run complete: 7 raw, 7 cleaned, 5 deduplicated."


def test_national_institution_registry_resolves_aliases_and_collaboration_type(tmp_path):
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text(
        "\n".join(
            [
                "institution_id,preferred_name,alternative_name,country_code,ror_id,parent_institution_id",
                "MY001,University of Example,UOE,MY,,",
                "MY002,National Research Institute,NRI,MY,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    registry = NationalInstitutionRegistry.from_csv(registry_path, country_code="MY")

    record = {
        "title": "National collaboration",
        "institutions": ["UOE", "NRI", "Foreign University"],
        "countries": ["MY", "US"],
    }
    enriched = enrich_national_context(record, registry, national_country_code="MY")

    assert enriched["national_association"] is True
    assert enriched["national_institution_ids"] == ["MY001", "MY002"]
    assert enriched["national_institutions"] == [
        "University of Example",
        "National Research Institute",
    ]
    assert enriched["unresolved_institutions"] == ["Foreign University"]
    assert enriched["collaboration_type"] == "international_collaboration"


def test_field_aware_analytics_skips_missing_metadata():
    summary = run_field_aware_analytics(
        [
            {"title": "A", "publication_year": 2020, "institutions": [], "authors": []},
            {"title": "B", "publication_year": 2021, "institutions": [], "authors": []},
        ]
    )

    assert summary["publications_by_year"] == {"2020": 1, "2021": 1}
    assert any("institution metadata is missing" in item for item in summary["skipped"])
    assert any("author metadata is missing" in item for item in summary["skipped"])


def test_cli_config_can_be_serialized_as_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project": {"name": "Serializable"},
                "input": {"path": "examples/sample_publications.csv", "format": "csv"},
            }
        ),
        encoding="utf-8",
    )

    config = load_config(config_path)

    assert config.project.name == "Serializable"
    assert config.input.format == "csv"


def test_registry_exposes_builtin_source_adapters():
    adapter_class = get_source_adapter("csv")

    assert adapter_class.__name__ == "CSVAdapter"
    assert "api" in SOURCE_REGISTRY
    assert "oai_pmh" in SOURCE_REGISTRY


def test_source_validation_preview_preserves_raw_and_source_specific_metadata(tmp_path):
    dataset = tmp_path / "custom.csv"
    dataset.write_text(
        "\n".join(
            [
                "paper_name,researcher_names,campus,published,department_code",
                "New source paper,A. Author; B. Author,Main Campus,Published in 2024,ENG",
                ",No Title Author,Main Campus,2023,SCI",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = config_from_dict(
        {
            "source": {
                "name": "new_university_repository",
                "type": "csv",
                "path": str(dataset),
            },
            "column_mapping": {
                "paper_name": "title",
                "researcher_names": "authors",
                "campus": "institutions",
                "published": "publication_year",
            },
            "transformations": {
                "publication_year": {"type": "extract_year"},
                "authors": {"type": "split", "separator": ";"},
            },
            "validation": {
                "required": ["title"],
                "require_any": ["authors", "publication_year", "source_record_id"],
            },
        }
    )

    pipeline = ResearchPipeline(config)
    report = pipeline.validate_source(sample_size=10)
    preview = pipeline.preview(limit=1)

    assert report.records_inspected == 2
    assert report.valid_records == 1
    assert report.invalid_records == 1
    assert report.missing_title == 1
    assert report.unmapped_columns == ["department_code"]
    assert preview[0]["publication_year"] == 2024
    assert preview[0]["authors"] == ["A. Author", "B. Author"]
    assert preview[0]["source_specific_metadata"] == {"department_code": "ENG"}
    assert preview[0]["raw_record"]["department_code"] == "ENG"


def test_generic_api_adapter_collects_paginated_records_and_transforms(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeSession:
        def __init__(self):
            self.headers = {}
            self.calls = []

        def request(self, method, url, params=None, timeout=None):
            self.calls.append((method, url, params, timeout))
            page = params.get("page", 1) if params else 1
            if page == 1:
                return FakeResponse(
                    {
                        "data": {
                            "publications": [
                                {
                                    "id": "api-1",
                                    "paperTitle": "API paper",
                                    "creatorNames": "A; B",
                                    "yearPublished": "2025-01-01",
                                    "faculty": "Engineering",
                                }
                            ]
                        },
                        "meta": {"next_page": 2},
                    }
                )
            return FakeResponse({"data": {"publications": []}, "meta": {"next_page": None}})

    fake_session = FakeSession()
    monkeypatch.setattr("research_analytics.adapters.api.requests.Session", lambda: fake_session)
    adapter = APIAdapter(
        base_url="https://example.test/publications",
        pagination={
            "type": "page",
            "page_parameter": "page",
            "page_size_parameter": "limit",
            "page_size": 1,
            "next_page_path": "meta.next_page",
            "max_pages": 2,
        },
        response={"records_path": "data.publications"},
        column_mapping={
            "id": "source_record_id",
            "paperTitle": "title",
            "creatorNames": "authors",
            "yearPublished": "publication_year",
        },
        transformations={
            "authors": {"type": "split", "separator": ";"},
            "publication_year": {"type": "extract_year"},
        },
        source_name="example_api",
    )

    records = list(adapter.collect())
    transformed = adapter.transform(records[0])

    assert len(records) == 1
    assert transformed["source_record_id"] == "api-1"
    assert transformed["title"] == "API paper"
    assert transformed["authors"] == ["A", "B"]
    assert transformed["publication_year"] == 2025
    assert transformed["source_specific_metadata"] == {"faculty": "Engineering"}
    assert adapter.validate(transformed) == []


def test_openalex_adapter_honors_configured_category_mapping():
    adapter = OpenAlexAdapter(
        country_code="SG",
        column_mapping={
            "openalex_id": "publication_id",
            "source_name": "journal",
            "concepts": "categories",
            "topics": "topics",
            "cited_by_count": "citation_count",
        },
        source_name="openalex_singapore",
    )

    transformed = adapter.transform(
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.123/example",
            "title": "Singapore category paper",
            "publication_year": 2026,
            "type": "article",
            "cited_by_count": 7,
            "primary_location": {
                "landing_page_url": "https://doi.org/10.123/example",
                "source": {
                    "display_name": "Example Journal",
                    "host_organization_name": "Example Publisher",
                },
            },
            "concepts": [
                {"display_name": "Computer science"},
                {"display_name": "Artificial intelligence"},
            ],
            "topics": [{"display_name": "Machine Learning"}],
            "abstract_inverted_index": {"Singapore": [0], "research": [1]},
            "awards": [{"id": "https://openalex.org/G1", "funder_display_name": "Grantor"}],
            "authorships": [
                {
                    "author": {"display_name": "A. Author"},
                    "countries": ["SG"],
                    "institutions": [
                        {
                            "display_name": "National University of Singapore",
                            "country_code": "SG",
                        }
                    ],
                }
            ],
        }
    )

    assert transformed["source_name"] == "openalex_singapore"
    assert transformed["journal"] == "Example Journal"
    assert transformed["categories"] == "Computer science; Artificial intelligence"
    assert transformed["topics"] == "Machine Learning"
    assert transformed["citation_count"] == 7
    assert transformed["raw_record"]["id"] == "https://openalex.org/W1"
    assert transformed["raw_record"]["awards"] == [
        {"id": "https://openalex.org/G1", "funder_display_name": "Grantor"}
    ]
    assert transformed["raw_record"]["abstract_inverted_index"] == {
        "Singapore": [0],
        "research": [1],
    }
    assert transformed["_provenance"]["raw_record_format"] == "openalex_api_work"


def test_openalex_adapter_can_restrict_collection_to_configured_country_only():
    class FakeCollector:
        def fetch_works(self, **kwargs):
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W-SG",
                        "title": "Singapore only",
                        "authorships": [
                            {
                                "countries": ["SG"],
                                "institutions": [
                                    {
                                        "display_name": "National University of Singapore",
                                        "country_code": "SG",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "id": "https://openalex.org/W-MIXED",
                        "title": "Singapore collaboration",
                        "authorships": [
                            {
                                "countries": ["SG", "US"],
                                "institutions": [
                                    {
                                        "display_name": "National University of Singapore",
                                        "country_code": "SG",
                                    },
                                    {
                                        "display_name": "Example US University",
                                        "country_code": "US",
                                    },
                                ],
                            }
                        ],
                    },
                ],
                "meta": {"next_cursor": None, "count": 2},
            }

    strict_adapter = OpenAlexAdapter(country_code="SG", strict_country_only=True)
    strict_adapter.collector = FakeCollector()
    broad_adapter = OpenAlexAdapter(country_code="SG", strict_country_only=False)
    broad_adapter.collector = FakeCollector()

    assert [record["id"] for record in strict_adapter.collect()] == ["https://openalex.org/W-SG"]
    assert [record["id"] for record in broad_adapter.collect()] == [
        "https://openalex.org/W-SG",
        "https://openalex.org/W-MIXED",
    ]
