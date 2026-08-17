import pytest

from src.api.repository import build_where
from src.api.routes import route_get
from src.api.service import APIError, ResearchLankaAPI


PUBLICATIONS = [
    {
        "publication_key": "doi:10.1000/test",
        "title": "Malaria surveillance in Sri Lanka",
        "doi": "10.1000/test",
        "publication_year": 2024,
        "type": "journal-article",
        "authors": "A. Author; B. Author",
        "institutions": "University of Colombo; University of Peradeniya",
        "sri_lankan_institutions": "University of Colombo",
        "countries": "LK; GB",
        "journal": "Ceylon Medical Journal",
        "publisher": "Example Publisher",
        "citation_count": 12,
        "reference_count": 30,
        "is_oa": True,
        "oa_status": "gold",
        "primary_field": "Medicine",
        "primary_subfield": "Public Health",
        "topics": "Epidemiology; Malaria",
        "concepts": "public health",
        "source_dataset": "openalex; crossref",
        "abstract": "A study abstract.",
        "citation_count_divergence_flag": False,
        "reference_count_divergence_flag": True,
        "raw_record": {"id": "W1"},
    },
    {
        "publication_key": "source:repositories:thesis-1",
        "title": "Repository-only thesis",
        "doi": None,
        "publication_year": 2023,
        "type": "thesis",
        "authors": "C. Author",
        "institutions": "University of Ruhuna",
        "sri_lankan_institutions": "University of Ruhuna",
        "countries": "LK",
        "journal": None,
        "publisher": "University of Ruhuna",
        "citation_count": 0,
        "reference_count": None,
        "is_oa": None,
        "oa_status": None,
        "primary_field": None,
        "primary_subfield": None,
        "topics": None,
        "concepts": None,
        "source_dataset": "repositories_combined",
        "abstract": None,
        "citation_count_divergence_flag": False,
        "reference_count_divergence_flag": False,
        "raw_record": {},
    },
]


class FakeRepository:
    def health(self):
        return True

    def metadata(self):
        return {
            "publication_count": len(PUBLICATIONS),
            "snapshot_date": "2026-07-20",
        }

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        rows = PUBLICATIONS
        if filters.get("year_min"):
            rows = [row for row in rows if row["publication_year"] >= filters["year_min"]]
        if filters.get("has_doi") is True:
            rows = [row for row in rows if row.get("doi")]
        if filters.get("has_doi") is False:
            rows = [row for row in rows if not row.get("doi")]
        if filters.get("q"):
            rows = [row for row in rows if filters["q"].casefold() in row["title"].casefold()]
        start = (page - 1) * page_size
        facets = {"publication_year": {"2024": 1, "2023": 1}} if include_facets else None
        return {
            "records": rows[start : start + page_size],
            "total": len(rows),
            "facets": facets,
            "meta": self.metadata(),
        }

    def get_publication(self, publication_key):
        return next((row for row in PUBLICATIONS if row["publication_key"] == publication_key), None)

    def get_references(self, publication_key):
        return [{"publication_key": publication_key, "reference_index": 1, "reference_title": "Ref"}]

    def get_count_audit(self, publication_key):
        if publication_key == PUBLICATIONS[0]["publication_key"]:
            return {"publication_key": publication_key, "citation_count": 12}
        return None

    def suggest(self, query, *, limit):
        return [{"type": "publication", "value": PUBLICATIONS[0]["title"], "key": PUBLICATIONS[0]["publication_key"]}][:limit]

    def semantic_search(self, query, *, filters, limit, min_score):
        row = {
            **PUBLICATIONS[0],
            "semantic_score": 0.925432,
            "semantic_rank": 1,
        }
        return [row][:limit]

    def related_publications(self, publication_key, *, filters, limit, min_score):
        if publication_key == "missing":
            raise KeyError(publication_key)
        row = {
            **PUBLICATIONS[1],
            "semantic_score": 0.812345,
            "semantic_rank": 1,
        }
        return [row][:limit]

    def researcher_profile(self, researcher_key):
        return {"key": "a-author", "label": researcher_key, "publication_count": 1}

    def researcher_publications(self, researcher_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def researcher_coauthors(self, researcher_key, *, limit):
        return [{"name": "B. Author", "publication_count": 1}]

    def institution_profile(self, institution_key):
        return {"key": "university-of-colombo", "label": institution_key, "publication_count": 1}

    def institution_publications(self, institution_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def institution_collaborators(self, institution_key, *, limit):
        return [{"institution": "University of Peradeniya", "publication_count": 1}]

    def compare_institutions(self, institution_keys):
        return [{"label": key, "publication_count": 1} for key in institution_keys]

    def topic_publications(self, topic_key, *, page, page_size):
        return {"records": [PUBLICATIONS[0]], "total": 1}

    def analytics_overview(self, filters):
        return {"publication_count": len(PUBLICATIONS), "doi_coverage": 0.5}

    def analytics_trends(self, filters, *, group_by, metric):
        return [{"key": 2024, "publication_count": 1, "citation_total": 12}]

    def analytics_rankings(self, filters, *, dimension, metric, limit):
        return [{"key": "medicine", "label": "Medicine", "publication_count": 1}]

    def collaboration_network(self, filters, *, scope, min_weight, limit):
        return {
            "nodes": [{"id": "university-of-colombo", "label": "University of Colombo"}],
            "edges": [],
        }

    def data_quality(self, filters, *, group_by):
        return {"record_count": len(PUBLICATIONS), "missing_doi_percentage": 50.0}


def api():
    return ResearchLankaAPI(FakeRepository())


def test_publication_list_maps_arrays_quality_flags_and_pagination():
    payload = api().list_publications({"include_facets": ["true"], "page_size": ["1"]})

    assert payload["pagination"] == {
        "page": 1,
        "page_size": 1,
        "total": 2,
        "total_pages": 2,
    }
    assert payload["data"][0]["authors"] == ["A. Author", "B. Author"]
    assert payload["data"][0]["source_dataset"] == ["openalex", "crossref"]
    assert "reference_count_divergence" in payload["data"][0]["quality_flags"]
    assert payload["facets"]["publication_year"]["2024"] == 1


def test_publication_detail_exposes_nested_contract_and_provenance():
    payload = api().publication_detail("doi:10.1000/test")

    assert payload["data"]["venue"]["journal"] == "Ceylon Medical Journal"
    assert payload["data"]["classification"]["topics"] == ["Epidemiology", "Malaria"]
    assert payload["data"]["provenance"]["raw_record_available"] is True


def test_publication_detail_raises_not_found():
    with pytest.raises(APIError) as exc_info:
        api().publication_detail("missing")

    assert exc_info.value.code == "not_found"
    assert exc_info.value.status == 404


def test_invalid_year_filter_raises_api_error():
    with pytest.raises(APIError) as exc_info:
        api().list_publications({"year_min": ["2025"], "year_max": ["2024"]})

    assert exc_info.value.code == "invalid_filter"


def test_compare_institutions_requires_two_or_three_values():
    with pytest.raises(APIError):
        api().compare_institutions({"institution": ["University of Colombo"]})

    payload = api().compare_institutions(
        {"institution": ["University of Colombo", "University of Peradeniya"]}
    )
    assert len(payload["data"]) == 2


def test_analytics_endpoints_delegate_to_repository():
    assert api().analytics_overview({})["data"]["publication_count"] == 2
    assert api().analytics_trends({"group_by": ["year"]})["data"][0]["key"] == 2024
    assert api().collaboration_network({"scope": ["institution"]})["data"]["nodes"]
    assert api().data_quality({})["data"]["missing_doi_percentage"] == 50.0


def test_publication_exports_use_filtered_summary_contract():
    csv_payload, csv_content_type = api().export_publications(
        {"has_doi": ["true"]},
        file_format="csv",
    )
    jsonl_payload, jsonl_content_type = api().export_publications(
        {"has_doi": ["true"]},
        file_format="jsonl",
    )

    assert csv_content_type == "text/csv; charset=utf-8"
    assert "Malaria surveillance in Sri Lanka" in csv_payload.decode("utf-8")
    assert "Repository-only thesis" not in csv_payload.decode("utf-8")
    assert jsonl_content_type == "application/x-ndjson; charset=utf-8"
    assert jsonl_payload.decode("utf-8").count("\n") == 1


def test_semantic_search_endpoint_shapes_scores_and_filters():
    payload = api().semantic_search(
        {
            "q": ["vector borne disease surveillance"],
            "year_min": ["2020"],
            "limit": ["5"],
            "min_score": ["0.5"],
        }
    )

    assert payload["data"][0]["title"] == "Malaria surveillance in Sri Lanka"
    assert payload["data"][0]["semantic_score"] == 0.925432
    assert payload["data"][0]["semantic_rank"] == 1
    assert payload["filters"]["applied"]["q"] == "vector borne disease surveillance"
    assert payload["filters"]["applied"]["year_min"] == 2020
    assert payload["meta"]["search"]["mode"] == "semantic"


def test_related_publications_route_and_missing_embedding():
    payload = route_get(
        api(),
        "/api/v1/publications/doi%3A10.1000%2Ftest/related",
        {"limit": ["3"]},
    )

    assert payload["data"][0]["title"] == "Repository-only thesis"
    assert payload["data"][0]["semantic_rank"] == 1

    with pytest.raises(APIError) as exc_info:
        api().related_publications("missing", {})

    assert exc_info.value.code == "not_found"
    assert exc_info.value.status == 404


def test_analytics_export_and_disabled_raw_payload():
    analytics_payload, content_type = api().export_analytics({}, name="overview")

    assert content_type == "text/csv; charset=utf-8"
    assert "publication_count" in analytics_payload.decode("utf-8")

    with pytest.raises(APIError) as exc_info:
        api().publication_raw("doi:10.1000/test")

    assert exc_info.value.code == "disabled_endpoint"
    assert exc_info.value.status == 403


def test_build_where_covers_core_filters():
    sql, params = build_where(
        {
            "q": "malaria",
            "year_min": 2020,
            "year_max": 2024,
            "type": ["journal-article"],
            "institution": ["University of Colombo"],
            "has_doi": True,
            "quality_flag": ["reference_count_divergence"],
        }
    )

    assert "publication_year >= %s" in sql
    assert "publication_year <= %s" in sql
    assert '"type" = ANY(%s)' in sql
    assert '"institutions" ILIKE %s' in sql
    assert "doi IS NOT NULL" in sql
    assert "reference_count_divergence_flag IS TRUE" in sql
    assert params[:4] == ["malaria", 2020, 2024, ["journal-article"]]
