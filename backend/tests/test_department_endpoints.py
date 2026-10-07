"""Tests for department portfolio endpoints served from the tagging sidecar."""

from __future__ import annotations

import asyncio
import csv
import io
import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from src.api.core.errors import APIError
from src.api.fastapi_app import create_app
from src.api.repositories import departments as department_repository
from src.api.repositories.departments import DepartmentStore
from src.api.routes import route_get
from src.api.service import ResearchLankaAPI
from src.api.services.departments import DepartmentService
from src.api.services.nmf_topics import NmfTopicService


PREFIX = "/api/v1/departments/uom-cse"

PUBLICATIONS = [
    {
        "publication_key": "doi:10.1000/a",
        "title": "Sinhala speech recognition with transformers",
        "doi": "10.1000/a",
        "publication_year": 2024,
        "type": "article",
        "authors": "Nadeesha Perera; Kasun Silva; Jane Doe",
        "institutions": "University of Moratuwa; University of Melbourne",
        "countries": "LK; AU",
        "journal": "Speech Journal",
        "citation_count": 10,
        "is_oa": True,
        "primary_topic": "Speech Recognition and Synthesis",
        "primary_subfield": "Artificial Intelligence",
        "source_dataset": "openalex",
    },
    {
        "publication_key": "doi:10.1000/b",
        "title": "Graph neural networks for traffic",
        "doi": "10.1000/b",
        "publication_year": 2022,
        "type": "article",
        "authors": "Kasun Silva",
        "institutions": "University of Moratuwa",
        "countries": "LK",
        "journal": "Traffic Journal",
        "citation_count": 4,
        "is_oa": False,
        "primary_topic": "Traffic Prediction",
        "primary_subfield": "Artificial Intelligence",
        "source_dataset": "openalex",
    },
    {
        # The loader canonicalised this record onto its OpenAlex key.
        "publication_key": "openalex:https://openalex.org/W3",
        "title": "Low-resource machine translation",
        "doi": None,
        "publication_year": 2024,
        "type": "article",
        "authors": "Nadeesha Perera",
        "institutions": "University of Moratuwa; Sri Lanka Institute of Information Technology",
        "countries": "LK",
        "journal": "Speech Journal",
        "citation_count": 1,
        "is_oa": True,
        "primary_topic": "Speech Recognition and Synthesis",
        "primary_subfield": "Artificial Intelligence",
        "source_dataset": "openalex",
    },
    {
        "publication_key": "doi:10.1000/other",
        "title": "Unrelated civil engineering paper",
        "doi": "10.1000/other",
        "publication_year": 2023,
        "type": "article",
        "authors": "Someone Else",
        "institutions": "University of Moratuwa",
        "countries": "LK",
        "journal": "Civil Journal",
        "citation_count": 50,
        "is_oa": True,
        "primary_topic": "Concrete",
        "primary_subfield": "Civil Engineering",
        "source_dataset": "openalex",
    },
]

SIDECAR_ROWS = [
    ("doi:10.1000/a", "10.1000/a", "https://openalex.org/W1", "explicit", "A1", "Nadeesha Perera", "explicit", 12,
     "Department of Computer Science and Engineering, University of Moratuwa"),
    ("doi:10.1000/a", "10.1000/a", "https://openalex.org/W1", "explicit", "A2", "Kasun Silva", "explicit", 3,
     "Dept. of CSE, University of Moratuwa"),
    ("doi:10.1000/b", "10.1000/b", "https://openalex.org/W2", "inferred", "A2", "Kasun Silva", "inferred", 3,
     "No unit named on this work; named CSE on 3 other works"),
    ("doi:10.1000/c", "10.1000/c", "https://openalex.org/W3", "explicit", "A1", "Nadeesha Perera", "explicit", 12,
     "Department of Computer Science & Engineering, University of Moratuwa"),
    # Tagged, but no longer served by the database.
    ("doi:10.1000/retired", "10.1000/retired", "https://openalex.org/W9", "explicit", "A1", "Nadeesha Perera",
     "explicit", 12, "Department of Computer Science and Engineering, University of Moratuwa"),
]


class FakeRepository:
    def health(self):
        return True

    def metadata(self):
        return {"publication_count": len(PUBLICATIONS)}

    def list_publications(self, filters, *, page, page_size, sort, include_facets):
        rows = list(PUBLICATIONS)
        keys = filters.get("publication_keys")
        if keys is not None:
            rows = [row for row in rows if row["publication_key"] in keys]
        if filters.get("year_min") is not None:
            rows = [row for row in rows if row["publication_year"] >= filters["year_min"]]
        if filters.get("year_max") is not None:
            rows = [row for row in rows if row["publication_year"] <= filters["year_max"]]
        if filters.get("q"):
            rows = [row for row in rows if filters["q"].casefold() in row["title"].casefold()]
        if sort == "citations_desc":
            rows.sort(key=lambda row: -row["citation_count"])
        else:
            rows.sort(key=lambda row: (-row["publication_year"], row["title"]))
        start = (page - 1) * page_size
        return {"records": rows[start : start + page_size], "total": len(rows), "facets": None}


class UnavailableNmf(NmfTopicService):
    def _require_store(self):
        raise APIError("service_unavailable", "No NMF artifacts.", status=503)


def write_sidecar(directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(
        [
            {
                "department_id": "uom-cse",
                "publication_key": key,
                "doi": doi,
                "openalex_id": openalex_id,
                "source_dataset": "openalex",
                "source_record_id": openalex_id,
                "publication_year": 2024,
                "title": "t",
                "publication_match": publication_match,
                "author_id": author_id,
                "author_name": name,
                "author_match": author_match,
                "author_department_works": works,
                "author_other_unit_works": 0,
                "evidence": evidence,
            }
            for key, doi, openalex_id, publication_match, author_id, name, author_match, works, evidence in SIDECAR_ROWS
        ]
    ).to_csv(directory / "department_publication_authors.csv", index=False)
    (directory / "department_tagging_summary.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-10-07T08:00:00+00:00",
                "departments": [
                    {
                        "department_id": "uom-cse",
                        "name": "Department of Computer Science and Engineering",
                        "short_name": "CSE",
                        "institution_id": "LK003",
                        "institution_name": "University of Moratuwa",
                        "faculty": "Faculty of Engineering",
                        "url": "https://cse.mrt.ac.lk",
                        "rules": {"min_history": 2, "dominance": 2.0},
                        "counts": {"institution_publications": 5, "department_publications": 4},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return directory


@pytest.fixture
def api(tmp_path: Path) -> ResearchLankaAPI:
    store = DepartmentStore(write_sidecar(tmp_path / "departments"))
    return ResearchLankaAPI(
        FakeRepository(),
        nmf_service=UnavailableNmf(),
        department_service=DepartmentService(store),
    )


def get(api: ResearchLankaAPI, path: str, **query: str):
    return route_get(api, path, {key: [value] for key, value in query.items()})


def test_store_resolves_aliases_and_prefers_explicit_evidence(tmp_path: Path):
    store = DepartmentStore(write_sidecar(tmp_path / "departments"))
    assignment = store.assignment_for("UOM-CSE", "openalex:https://openalex.org/W3")
    assert assignment is not None
    assert assignment["publication_key"] == "doi:10.1000/c"
    assert store.assignment_for("uom-cse", "doi:10.1000/a")["evidence"].startswith("Department of Computer")
    assert set(store.candidate_keys("uom-cse", match="inferred")) == {
        "doi:10.1000/b",
        "openalex:https://openalex.org/W2",
    }


def test_list_departments(api: ResearchLankaAPI):
    payload = get(api, "/api/v1/departments")
    (department,) = payload["data"]
    assert department["department_id"] == "uom-cse"
    assert department["institution_name"] == "University of Moratuwa"
    assert department["tagged_publication_count"] == 4


def test_department_profile_counts_only_served_publications(api: ResearchLankaAPI):
    data = get(api, PREFIX)["data"]

    assert data["publication_count"] == 3
    assert (data["explicit_count"], data["inferred_count"]) == (2, 1)
    assert data["researcher_count"] == 2
    assert data["citation_total"] == 15
    assert data["h_index"] == 2
    assert data["open_access_share"] == pytest.approx(2 / 3)
    assert data["international_share"] == pytest.approx(1 / 3)
    assert (data["year_min"], data["year_max"]) == (2022, 2024)
    assert data["yearly"] == [
        {"year": 2022, "publication_count": 1, "explicit_count": 0, "inferred_count": 1},
        {"year": 2024, "publication_count": 2, "explicit_count": 2, "inferred_count": 0},
    ]
    assert data["research_areas"][0] == {"label": "Speech Recognition and Synthesis", "publication_count": 2}
    assert {(row["label"], row["publication_count"]) for row in data["partner_institutions"]} == {
        ("University of Melbourne", 1),
        ("Sri Lanka Institute of Information Technology", 1),
    }
    assert data["partner_countries"] == [{"label": "AU", "publication_count": 1}]
    assert [row["label"] for row in data["top_researchers"]] == ["Kasun Silva", "Nadeesha Perera"]
    assert data["top_cited"][0]["publication_key"] == "doi:10.1000/a"
    assert data["top_cited"][0]["department"]["match"] == "explicit"
    assert data["method"]["coverage"]["institution_publications"] == 5


def test_department_profile_year_filter(api: ResearchLankaAPI):
    data = get(api, PREFIX, year_min="2023")["data"]
    assert data["publication_count"] == 2
    assert data["inferred_count"] == 0


def test_department_publications_filters_and_annotations(api: ResearchLankaAPI):
    payload = get(api, f"{PREFIX}/publications")
    assert payload["pagination"]["total"] == 3
    keys = [row["publication_key"] for row in payload["data"]]
    assert "openalex:https://openalex.org/W3" in keys
    w3 = next(row for row in payload["data"] if row["publication_key"].startswith("openalex:"))
    assert w3["department"]["authors"] == [{"name": "Nadeesha Perera", "author_id": "A1", "match": "explicit"}]

    inferred = get(api, f"{PREFIX}/publications", match="inferred")
    assert [row["publication_key"] for row in inferred["data"]] == ["doi:10.1000/b"]
    assert "named CSE on 3 other works" in inferred["data"][0]["department"]["evidence"]

    by_researcher = get(api, f"{PREFIX}/publications", researcher="nadeesha perera")
    assert by_researcher["pagination"]["total"] == 2

    by_id = get(api, f"{PREFIX}/publications", researcher="A2")
    assert by_id["pagination"]["total"] == 2

    searched = get(api, f"{PREFIX}/publications", q="translation")
    assert [row["title"] for row in searched["data"]] == ["Low-resource machine translation"]


def test_department_researchers(api: ResearchLankaAPI):
    payload = get(api, f"{PREFIX}/researchers")
    assert payload["pagination"]["total"] == 2
    silva, perera = payload["data"]
    assert silva["label"] == "Kasun Silva"
    assert (silva["publication_count"], silva["explicit_count"], silva["inferred_count"]) == (2, 1, 1)
    assert silva["citation_total"] == 14
    assert (silva["first_year"], silva["last_year"]) == (2022, 2024)
    assert perera["department_works"] == 12
    assert perera["top_areas"] == ["Speech Recognition and Synthesis"]

    assert [row["label"] for row in get(api, f"{PREFIX}/researchers", q="perera")["data"]] == ["Nadeesha Perera"]
    assert [row["label"] for row in get(api, f"{PREFIX}/researchers", sort="name_asc")["data"]] == [
        "Kasun Silva",
        "Nadeesha Perera",
    ]


def test_department_export_csv(api: ResearchLankaAPI):
    body, content_type = get(api, f"{PREFIX}/publications.csv")
    assert content_type.startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(body.decode("utf-8"))))
    assert len(rows) == 3
    first = next(row for row in rows if row["publication_key"] == "doi:10.1000/a")
    assert first["department_match"] == "explicit"
    assert first["department_authors"] == "Nadeesha Perera; Kasun Silva"
    assert first["authors"] == "Nadeesha Perera; Kasun Silva; Jane Doe"


@pytest.mark.parametrize(
    ("path", "query", "code"),
    [
        ("/api/v1/departments/nope", {}, "not_found"),
        (f"{PREFIX}/publications", {"match": "maybe"}, "invalid_filter"),
        (f"{PREFIX}/publications", {"institution": "x"}, "invalid_query_parameter"),
        (f"{PREFIX}/researchers", {"sort": "loudest"}, "invalid_sort"),
    ],
)
def test_department_errors(api: ResearchLankaAPI, path: str, query: dict[str, str], code: str):
    with pytest.raises(APIError) as excinfo:
        get(api, path, **query)
    assert excinfo.value.code == code


def test_missing_artifacts_report_service_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DEPARTMENT_ARTIFACT_DIR", str(tmp_path / "missing"))
    department_repository.get_department_store.cache_clear()
    try:
        api = ResearchLankaAPI(FakeRepository(), nmf_service=UnavailableNmf())
        with pytest.raises(APIError) as excinfo:
            get(api, "/api/v1/departments")
        assert excinfo.value.status == 503
    finally:
        department_repository.get_department_store.cache_clear()


def test_fastapi_routes_serve_departments(api: ResearchLankaAPI):
    app = create_app(publication_service=api)

    async def fetch(path: str) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(path)

    profile = asyncio.run(fetch(PREFIX))
    assert profile.status_code == 200
    assert profile.json()["data"]["publication_count"] == 3

    researchers = asyncio.run(fetch(f"{PREFIX}/researchers"))
    assert researchers.json()["pagination"]["total"] == 2

    export = asyncio.run(fetch(f"{PREFIX}/publications.csv"))
    assert export.status_code == 200
    assert export.headers["content-type"].startswith("text/csv")

    missing = asyncio.run(fetch("/api/v1/departments/nope"))
    assert missing.status_code == 404
