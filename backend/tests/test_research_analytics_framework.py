import csv
import json
from datetime import date, datetime

from research_analytics import ResearchPipeline, load_config, map_to_standard_schema
from research_analytics.adapters import SOURCE_REGISTRY
from research_analytics.adapters.api import APIAdapter
from research_analytics.adapters.openalex import OpenAlexAdapter
from research_analytics.adapters.registry import get_source_adapter
from research_analytics.analytics import run_field_aware_analytics
from research_analytics.cli import run_stage
from research_analytics.cleaning import (
    normalize_publication_date,
    normalize_publication_year,
    normalize_title,
    normalize_title_key,
)
from research_analytics.config import config_from_dict
from research_analytics.institutions import NationalInstitutionRegistry, enrich_national_context
from research_analytics.networks import build_author_collaboration_network
from research_analytics.schema import STANDARD_PUBLICATION_FIELDS
from research_analytics.validation import record_validation_errors, validate_records


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


def test_author_collaboration_network_uses_disambiguated_ids_and_years():
    network = build_author_collaboration_network(
        [
            {
                "publication_id": "p1",
                "authors": "Perera, K.; Silva, A.",
                "author_ids": "author-perera; author-silva",
                "publication_year": "2022",
            },
            {
                "publication_id": "p2",
                "authors": "Perera, Kumara; Silva, A.; Fernando, N.",
                "author_ids": "author-perera; author-silva; author-fernando",
                "publication_year": "2024",
            },
        ]
    )

    assert {
        (edge["source"], edge["target"]): edge
        for edge in network["edges"]
    }[("author-perera", "author-silva")] == {
        "source": "author-perera",
        "target": "author-silva",
        "source_label": "Perera, K.",
        "target_label": "Silva, A.",
        "weight": 2,
        "edge_type": "author_collaboration",
        "first_year": 2022,
        "last_year": 2024,
    }
    assert {node["id"] for node in network["nodes"]} == {
        "author-perera",
        "author-silva",
        "author-fernando",
    }


def test_pipeline_runs_from_configuration_and_exports_reports(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,paper_name,researcher,university,published_year,doi,citation_count",
                "1,Same title,A. Author,Example University,2022,https://doi.org/10.1000/ABC,4",
                "2,Same title,A Author,EU,2022,10.1000/abc,4",
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
                "country_name": "Sri Lanka",
                "country_code": "LK",
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


def test_pipeline_rejects_invalid_doi_values(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,title,authors,publication_year,doi",
                "1,Valid DOI paper,A. Author,2024,10.1234/good",
                "2,Invalid DOI paper,B. Author,2024,not-a-doi",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = config_from_dict(
        {
            "source": {"name": "doi_validation_test", "type": "csv", "path": str(dataset)},
            "column_mapping": {
                "record_id": "source_record_id",
                "title": "title",
                "authors": "authors",
                "publication_year": "publication_year",
                "doi": "doi",
            },
            "pipeline": {"export": False},
        }
    )

    result = ResearchPipeline(config).run_all()

    assert result.validation_report is not None
    assert result.validation_report.invalid_doi_count == 1
    assert len(result.valid_records) == 1
    assert len(result.invalid_records) == 1
    assert result.invalid_records[0]["_validation_errors"] == ["Invalid DOI value: doi"]
    assert len(result.cleaned_records) == 1


def test_pipeline_removes_invalid_publication_records_from_outputs(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,title,authors,publication_year,doi",
                "1,Valid paper,A. Author,2024,10.1234/good",
                "2,,B. Author,2024,10.1234/missing-title",
                "3,Invalid year,C. Author,2099,10.1234/bad-year",
                "4,Invalid DOI,D. Author,2024,not-a-doi",
                ",No identifiers,,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    output_dir = tmp_path / "outputs"
    config = config_from_dict(
        {
            "source": {"name": "invalid_record_removal_test", "type": "csv", "path": str(dataset)},
            "column_mapping": {
                "record_id": "source_record_id",
                "title": "title",
                "authors": "authors",
                "publication_year": "publication_year",
                "doi": "doi",
            },
            "cleaning": {"valid_year": {"minimum": 1950, "maximum": 2026}},
            "export": {"output_dir": str(output_dir)},
        }
    )

    result = ResearchPipeline(config).run_all()

    assert result.validation_report is not None
    assert result.validation_report.invalid_year_count == 1
    assert result.validation_report.invalid_doi_count == 1
    assert len(result.valid_records) == 1
    assert len(result.invalid_records) == 4
    assert len(result.cleaned_records) == 1
    assert len(result.deduplicated_records) == 1
    assert result.cleaned_records[0]["title"] == "Valid paper"

    with (output_dir / "cleaned_publications.csv").open(newline="", encoding="utf-8") as f:
        cleaned_rows = list(csv.DictReader(f))
    with (output_dir / "deduplicated_publications.csv").open(newline="", encoding="utf-8") as f:
        deduplicated_rows = list(csv.DictReader(f))
    processing_errors = json.loads((output_dir / "processing_errors.json").read_text())
    processing_report = json.loads((output_dir / "processing_report.json").read_text())

    assert [row["title"] for row in cleaned_rows] == ["Valid paper"]
    assert [row["title"] for row in deduplicated_rows] == ["Valid paper"]
    assert len(processing_errors) == 4
    assert any(
        error["title"] == "No identifiers"
        and error["_validation_errors"]
        == [
            "At least one identifying field is required: "
            "doi, authors, publication_year, source_record_id"
        ]
        for error in processing_errors
    )
    assert processing_report["removed_invalid_record_count"] == 4
    assert processing_report["removed_unusable_record_count"] == 4


def test_validation_reports_doi_year_and_source_consistency():
    config = config_from_dict(
        {
            "source": {"name": "expected_source", "type": "csv", "path": "unused.csv"},
            "cleaning": {"valid_year": {"minimum": 2000, "maximum": 2030}},
        }
    )
    records = [
        {
            "source_name": "expected_source",
            "source_record_id": "record-1",
            "doi": "10.1000/shared",
            "title": "Shared DOI paper",
            "publication_year": "2024",
            "publication_date": "2024-05-01",
        },
        {
            "source_name": "expected_source",
            "source_record_id": "record-2",
            "doi": "https://doi.org/10.1000/shared",
            "title": "Shared DOI paper",
            "publication_year": "2023",
            "publication_date": "2023",
        },
        {
            "source_name": "expected_source",
            "source_record_id": "record-1",
            "doi": "10.1000/source-conflict",
            "title": "Different source record paper",
            "publication_year": "2024",
            "publication_date": "2024",
        },
        {
            "source_name": "wrong_source",
            "source_record_id": "record-3",
            "doi": "10.1000/wrong-source",
            "title": "Wrong source paper",
            "publication_year": "2022",
            "publication_date": "2021-12-01",
        },
        {
            "source_name": "",
            "source_record_id": "record-4",
            "doi": "not-a-doi",
            "title": "Missing source paper",
            "publication_year": "2099",
            "publication_date": "2099",
        },
    ]

    report = validate_records(records, config)

    assert report.invalid_doi_count == 1
    assert report.invalid_year_count == 1
    assert report.year_date_mismatch_count == 1
    assert report.missing_source_count == 1
    assert report.source_name_mismatch_count == 1
    assert report.duplicate_source_record_count == 1
    assert report.source_record_conflict_count == 1
    assert report.doi_year_conflict_count == 1
    assert report.doi_title_conflict_count == 0
    assert report.consistency_issue_count == 6
    assert {
        "year_date_mismatch",
        "missing_source",
        "source_name_mismatch",
        "duplicate_source_record",
        "source_record_conflict",
        "doi_year_conflict",
    } == {issue["issue_type"] for issue in report.consistency_issues}


def test_record_validation_rejects_year_date_and_source_mismatches():
    config = config_from_dict(
        {
            "source": {"name": "expected_source", "type": "csv", "path": "unused.csv"},
            "cleaning": {"valid_year": {"minimum": 2000, "maximum": 2030}},
        }
    )
    record = {
        "source_name": "wrong_source",
        "source_record_id": "record-1",
        "doi": "10.1000/test",
        "title": "Mismatched paper",
        "publication_year": "2024",
        "publication_date": "2023-12-31",
    }

    assert record_validation_errors(record, config) == [
        "Publication year does not match publication_date year",
        "Unexpected source name: source_name must match expected_source",
    ]


def test_title_normalization_cleans_markup_entities_and_spacing():
    title = (
        "  Fired-Siltstone Based Geopolymers for CO&lt;inf&gt;2&lt;/inf&gt; "
        "Sequestration Wells &amp;amp; Storage  "
    )

    assert (
        normalize_title(title)
        == "Fired-Siltstone Based Geopolymers for CO2 Sequestration Wells & Storage"
    )
    assert (
        normalize_title_key(title)
        == "fired siltstone based geopolymers for co2 sequestration wells storage"
    )


def test_title_key_preserves_unicode_words():
    theory = "තොරතුරු තාක්ෂණය පිළිබඳ පදනම් පාඨමාලාව (සිද්ධාන්ත) - FNDI 22020"
    practical = "තොරතුරු තාක්ෂණය පිළිබඳ පදනම් පාඨමාලාව (ප්‍රායෝගික) - FNDI 22020"

    assert normalize_title_key(theory) != normalize_title_key(practical)
    assert "සිද්ධාන්ත" in normalize_title_key(theory)
    assert "ප්‍රායෝගික" in normalize_title_key(practical)


def test_pipeline_writes_normalized_publication_title(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,title,authors,publication_year",
                "1,<scp>I</scp>slam and Gender,A. Author,2024",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = config_from_dict(
        {
            "source": {"name": "title_normalization_test", "type": "csv", "path": str(dataset)},
            "column_mapping": {
                "record_id": "source_record_id",
                "title": "title",
                "authors": "authors",
                "publication_year": "publication_year",
            },
            "pipeline": {"export": False},
        }
    )

    result = ResearchPipeline(config).run_all()

    assert result.cleaned_records[0]["title"] == "Islam and Gender"
    assert result.cleaned_records[0]["normalized_title"] == "islam and gender"
    assert result.cleaned_records[0]["processing_status"] == "cleaned"


def test_transform_stage_can_apply_shared_cleaning_functions(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,title,authors,publication_date,publication_year,doi,keywords",
                (
                    "1,<scp>I</scp>slam and Gender,A. Author; B. Author,"
                    "2024-03-15T12:30:00,Published in 2024,"
                    "https://doi.org/10.1234/ABC,AI; ML"
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = config_from_dict(
        {
            "source": {"name": "cleaning_transform_test", "type": "csv", "path": str(dataset)},
            "column_mapping": {
                "record_id": "source_record_id",
                "title": "title",
                "authors": "authors",
                "publication_date": "publication_date",
                "publication_year": "publication_year",
                "doi": "doi",
                "keywords": "keywords",
            },
            "transformations": {
                "title": {"type": "normalize_title"},
                "authors": {"type": "normalize_list"},
                "publication_date": {"type": "normalize_publication_date"},
                "publication_year": {"type": "normalize_publication_year"},
                "doi": {"type": "normalize_doi"},
                "keywords": {"type": "normalize_list_like"},
            },
            "pipeline": {"export": False},
        }
    )

    pipeline = ResearchPipeline(config)
    pipeline.collect()
    transformed = pipeline.transform()

    assert transformed[0]["title"] == "Islam and Gender"
    assert transformed[0]["authors"] == ["A. Author", "B. Author"]
    assert transformed[0]["publication_date"] == "2024-03-15"
    assert transformed[0]["publication_year"] == 2024
    assert transformed[0]["doi"] == "10.1234/abc"
    assert transformed[0]["keywords"] == ["AI", "ML"]


def test_publication_date_normalization_handles_common_source_shapes():
    assert normalize_publication_date("2024") == "2024"
    assert normalize_publication_date("2024-3") == "2024-03"
    assert normalize_publication_date("2024-03-15T12:30:00") == "2024-03-15"
    assert normalize_publication_date(date(2024, 3, 15)) == "2024-03-15"
    assert normalize_publication_date(datetime(2024, 3, 15, 12, 30)) == "2024-03-15"
    assert normalize_publication_date({"date-parts": [[2024, 3, 15]]}) == "2024-03-15"
    assert normalize_publication_date("[[2024, 3]]") == "2024-03"
    assert normalize_publication_date("15/03/2024") == "2024-03-15"
    assert normalize_publication_date("2024-99-99") == "2024"
    assert normalize_publication_date("not-a-date") is None


def test_publication_year_normalization_extracts_from_date_values():
    assert normalize_publication_year("2024-03-15") == 2024
    assert normalize_publication_year({"date-parts": [[2024, 3, 15]]}) == 2024
    assert normalize_publication_year("[[2024, 3]]") == 2024
    assert normalize_publication_year(2024.0) == 2024
    assert normalize_publication_year("not-a-year") is None


def test_pipeline_normalizes_publication_date_and_fills_year(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,title,authors,publication_date,publication_year",
                "1,Date paper,A. Author,2024-03-15T12:30:00,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = config_from_dict(
        {
            "source": {"name": "date_normalization_test", "type": "csv", "path": str(dataset)},
            "column_mapping": {
                "record_id": "source_record_id",
                "title": "title",
                "authors": "authors",
                "publication_date": "publication_date",
                "publication_year": "publication_year",
            },
            "pipeline": {"export": False},
        }
    )

    result = ResearchPipeline(config).run_all()

    assert result.cleaned_records[0]["publication_date"] == "2024-03-15"
    assert result.cleaned_records[0]["publication_year"] == 2024


def test_pipeline_loads_database_when_enabled(tmp_path, monkeypatch):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,title,authors,institutions,publication_year,doi",
                "1,Database paper,A. Author,Example University,2024,10.1000/db",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    loaded_batches = []

    def fake_load_final_publications(records):
        loaded_batches.append(records)
        return len(records)

    monkeypatch.setattr(
        "src.database.loader.load_final_publications",
        fake_load_final_publications,
    )
    config = config_from_dict(
        {
            "source": {"name": "database_test", "type": "csv", "path": str(dataset)},
            "column_mapping": {
                "record_id": "source_record_id",
                "title": "title",
                "authors": "authors",
                "institutions": "institutions",
                "publication_year": "publication_year",
                "doi": "doi",
            },
            "pipeline": {"load_database": True, "export": False},
        }
    )

    result = ResearchPipeline(config).run_all()

    assert result.database_load_count == 1
    assert len(loaded_batches) == 1
    assert loaded_batches[0][0]["title"] == "Database paper"


def test_sri_lanka_project_country_is_supplied_by_config_not_pipeline_code(tmp_path):
    config = load_config("configurations/sri_lanka/config.json")

    assert config.project.country_code == "LK"
    assert config.project.country_name == "Sri Lanka"
    assert config.institution_registry.path == "configurations/sri_lanka/institutions.csv"
    assert config.input.path == "data/processed/repositories_combined.csv"
    assert config.sources["openalex"]["options"]["strict_country_only"] is True


def test_sri_lanka_source_config_shape_can_select_first_enabled_source():
    config = config_from_dict(
        {
            "country": {"name": "Sri Lanka", "code": "LK"},
            "coverage": {"start_year": 2020, "end_year": 2026},
            "institution_registry": "configurations/sri_lanka/institutions.csv",
            "sources": {
                "openalex": {
                    "enabled": True,
                    "endpoint": "https://api.openalex.org/works",
                    "filter": "institutions.country_code:LK",
                    "options": {"max_records": 10, "strict_country_only": True},
                },
                "local_repository": {
                    "enabled": False,
                    "adapter": "oai_pmh",
                    "endpoint": "https://repo.example.invalid/oai",
                },
            },
            "dashboard": {"title": "Sri Lankan Research Portal"},
        }
    )

    assert config.project.country_name == "Sri Lanka"
    assert config.project.country_code == "LK"
    assert config.project.dashboard_title == "Sri Lankan Research Portal"
    assert config.collection.start_year == 2020
    assert config.source.name == "openalex"
    assert config.source.type == "openalex"
    assert config.source.base_url == "https://api.openalex.org/works"
    assert config.source.filter == "institutions.country_code:LK"
    assert config.source.options["strict_country_only"] is True
    assert config.institution_registry.path == "configurations/sri_lanka/institutions.csv"


def test_stage_runner_executes_all_pipeline_steps_from_sri_lanka_shaped_config(tmp_path):
    dataset = tmp_path / "publications.csv"
    dataset.write_text(
        "\n".join(
            [
                "record_id,title,authors,institutions,publication_year,doi",
                "1,Same title,A. Author,University of Colombo,2022,https://doi.org/10.1000/ABC",
                "2,Same title,A Author,UOC,2022,10.1000/abc",
                "3,Another title,B. Author,University of Peradeniya,2023,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    config = config_from_dict(
        {
            "country": {"name": "Sri Lanka", "code": "LK"},
            "source": {"name": "sri_lanka_test_dataset", "type": "csv", "path": str(dataset)},
            "column_mapping": {
                "record_id": "source_record_id",
                "title": "title",
                "authors": "authors",
                "institutions": "institutions",
                "publication_year": "publication_year",
                "doi": "doi",
            },
            "export": {"output_dir": str(tmp_path / "outputs")},
        }
    )
    output = run_stage(ResearchPipeline(config), "all")

    assert output == "Run complete: 3 raw, 3 cleaned, 2 deduplicated."


def test_national_institution_registry_resolves_aliases_and_collaboration_type(tmp_path):
    registry_path = tmp_path / "institutions.csv"
    registry_path.write_text(
        "\n".join(
            [
                "institution_id,preferred_name,alternative_name,country_code,ror_id,parent_institution_id",
                "LK001,University of Colombo,UOC,LK,,",
                "LK002,National Research Institute,NRI,LK,,",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    registry = NationalInstitutionRegistry.from_csv(registry_path, country_code="LK")

    record = {
        "title": "National collaboration",
        "institutions": ["UOC", "NRI", "Foreign University"],
        "countries": ["LK", "US"],
    }
    enriched = enrich_national_context(record, registry, national_country_code="LK")

    assert enriched["national_association"] is True
    assert enriched["national_institution_ids"] == ["LK001", "LK002"]
    assert enriched["national_institutions"] == [
        "University of Colombo",
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
    dataset = tmp_path / "publications.csv"
    dataset.write_text("title\nSri Lanka paper\n", encoding="utf-8")
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps(
            {
                "project": {"name": "Serializable"},
                "input": {"path": str(dataset), "format": "csv"},
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
        country_code="LK",
        column_mapping={
            "openalex_id": "publication_id",
            "source_name": "journal",
            "concepts": "categories",
            "topics": "topics",
            "cited_by_count": "citation_count",
        },
        source_name="openalex_sri_lanka",
    )

    transformed = adapter.transform(
        {
            "id": "https://openalex.org/W1",
            "doi": "https://doi.org/10.123/example",
            "title": "Sri Lanka category paper",
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
            "abstract_inverted_index": {"Sri": [0], "Lanka": [1], "research": [2]},
            "awards": [{"id": "https://openalex.org/G1", "funder_display_name": "Grantor"}],
            "authorships": [
                {
                    "author": {"display_name": "A. Author"},
                    "countries": ["LK"],
                    "institutions": [
                        {
                            "display_name": "University of Colombo",
                            "country_code": "LK",
                        }
                    ],
                }
            ],
        }
    )

    assert transformed["source_name"] == "openalex_sri_lanka"
    assert transformed["journal"] == "Example Journal"
    assert transformed["categories"] == "Computer science; Artificial intelligence"
    assert transformed["topics"] == "Machine Learning"
    assert transformed["citation_count"] == 7
    assert transformed["raw_record"]["id"] == "https://openalex.org/W1"
    assert transformed["raw_record"]["awards"] == [
        {"id": "https://openalex.org/G1", "funder_display_name": "Grantor"}
    ]
    assert transformed["raw_record"]["abstract_inverted_index"] == {
        "Sri": [0],
        "Lanka": [1],
        "research": [2],
    }
    assert transformed["_provenance"]["raw_record_format"] == "openalex_api_work"


def test_openalex_adapter_can_restrict_collection_to_configured_country_only():
    class FakeCollector:
        def fetch_works(self, **kwargs):
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W-LK",
                        "title": "Sri Lanka only",
                        "authorships": [
                            {
                                "countries": ["LK"],
                                "institutions": [
                                    {
                                        "display_name": "University of Colombo",
                                        "country_code": "LK",
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "id": "https://openalex.org/W-MIXED",
                        "title": "Sri Lanka collaboration",
                        "authorships": [
                            {
                                "countries": ["LK", "US"],
                                "institutions": [
                                    {
                                        "display_name": "University of Colombo",
                                        "country_code": "LK",
                                    },
                                    {
                                        "display_name": "Example US University",
                                        "country_code": "US",
                                    },
                                ],
                            }
                        ],
                    },
                    {
                        "id": "https://openalex.org/W-FOREIGN-LED",
                        "title": "Foreign-led Sri Lanka collaboration",
                        "authorships": [
                            {
                                "author_position": "first",
                                "countries": ["GB"],
                                "institutions": [
                                    {
                                        "display_name": "University of Edinburgh",
                                        "country_code": "GB",
                                    }
                                ],
                            },
                            {
                                "countries": ["LK"],
                                "institutions": [
                                    {
                                        "display_name": "University of Colombo",
                                        "country_code": "LK",
                                    }
                                ],
                            },
                        ],
                    },
                ],
                "meta": {"next_cursor": None, "count": 3},
            }

    strict_adapter = OpenAlexAdapter(country_code="LK", strict_country_only=True)
    strict_adapter.collector = FakeCollector()
    broad_adapter = OpenAlexAdapter(country_code="LK", strict_country_only=False)
    broad_adapter.collector = FakeCollector()

    assert [record["id"] for record in strict_adapter.collect()] == ["https://openalex.org/W-LK"]
    assert [record["id"] for record in broad_adapter.collect()] == [
        "https://openalex.org/W-LK",
        "https://openalex.org/W-MIXED",
    ]
