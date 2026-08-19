# API Design

**Status:** MVP read-only API implemented with standard-library HTTP server; initial FastAPI model endpoints added; production hardening pending  
**Scope:** Read-only public API for the Sri Lanka national research analytics platform  
**Primary datastore:** PostgreSQL `final_publications` plus sidecar/audit tables  
**Related docs:** [frontend_requirements.md](frontend_requirements.md), [metadata.md](metadata.md), [10_data_cleaning_rules.md](10_data_cleaning_rules.md), [11_metadata_quality_limitations.md](11_metadata_quality_limitations.md)

## 1. Purpose

The API exposes the cleaned national publication corpus to the dashboard,
profile pages, search interface, export workflows, and future analytical
services. It is not an ingestion API. Source collection, cleaning,
deduplication, and PostgreSQL loading remain batch pipeline responsibilities.

The first implementation should be read-only, unauthenticated, and versioned
under `/api/v1`.

## 2. Design Principles

| Principle | Requirement |
|---|---|
| Read-only MVP | No user edits, claims, corrections, or source mutations in the first public API. |
| Evidence-aware | Responses expose source provenance, data-quality warnings, and known limitations where relevant. |
| Stable canonical fields | Public response fields are based on `final_publications`, not raw source schemas. |
| Filterable by default | Publication listings support structured filters used by the dashboard and search UI. |
| Paginated responses | Every list endpoint uses explicit pagination and a maximum page size. |
| Safe null semantics | Missing values are returned as `null` or empty arrays, never string placeholders such as `"nan"`. |
| Snapshot transparency | Metadata endpoints expose source snapshot/load information so charts can cite the data vintage. |
| Implementation simplicity | MVP endpoints should be expressible with SQL over PostgreSQL plus small response mappers. |

## 3. API Base and Versioning

```text
Base path: /api/v1
Format: JSON by default
CSV export endpoints: text/csv
Timezone: UTC for timestamps
Date format: YYYY-MM-DD
Pagination: page/page_size for MVP; cursor pagination can be added later
```

Versioning rules:

- Additive response fields may be introduced within `v1`.
- Renaming, removing, or changing field meaning requires `v2`.
- Deprecated fields must stay for one release cycle after a replacement is
  documented.

## 3.1 Implementation Organization

The API implementation is split by responsibility under `src/api/`:

| File | Responsibility |
|---|---|
| `server.py` | HTTP request/response mechanics, CORS, CLI server startup. |
| `fastapi_app.py` | FastAPI app factory, model-serving routes, OpenAPI docs, and Uvicorn CLI startup. |
| `routes.py` | Versioned route dispatch from URL paths to service methods. |
| `service.py` | Endpoint use cases, repository orchestration, and response envelopes. |
| `model_service.py` | Publication classifier loading, readiness reporting, and prediction response shaping. |
| `repository.py` | PostgreSQL access for publications, profiles, facets, and analytics. |
| `query.py` | Query-string parsing and validation. |
| `serializers.py` | Public response contracts, normalization, and quality flags. |
| `exports.py` | CSV and JSONL export serialization. |
| `sql.py` | SQL column lists, sort expressions, filters, and quoting helpers. |
| `aggregates.py` | Shared profile and analytics aggregate helpers. |
| `constants.py`, `errors.py`, `protocols.py` | Shared API constants, exceptions, and storage contracts. |

## 4. Core Resource Model

### Publication Summary

Used in list/search results.

```json
{
  "publication_key": "doi:10.1000/example",
  "title": "Example publication title",
  "doi": "10.1000/example",
  "publication_year": 2024,
  "type": "journal-article",
  "authors": ["A. Author", "B. Author"],
  "institutions": ["University of Colombo"],
  "journal": "Example Journal",
  "publisher": "Example Publisher",
  "citation_count": 12,
  "reference_count": 30,
  "is_oa": true,
  "oa_status": "gold",
  "primary_field": "Medicine",
  "primary_subfield": "Public Health",
  "source_dataset": ["openalex", "crossref"],
  "quality_flags": ["reference_count_divergence"]
}
```

### Publication Detail

Extends the summary with abstract, identifiers, provenance, topics, funding,
license, count divergence, and raw-record availability metadata.

```json
{
  "publication_key": "doi:10.1000/example",
  "title": "Example publication title",
  "abstract": "Abstract text when available.",
  "doi": "10.1000/example",
  "openalex_id": "https://openalex.org/W123",
  "url": "https://example.org/work",
  "pdf_url": null,
  "publication_year": 2024,
  "publication_date": "2024-01-15",
  "type": "journal-article",
  "authors": ["A. Author", "B. Author"],
  "author_orcids": ["https://orcid.org/0000-0000-0000-0000"],
  "institutions": ["University of Colombo"],
  "sri_lankan_institutions": ["University of Colombo"],
  "countries": ["LK", "GB"],
  "venue": {
    "journal": "Example Journal",
    "publisher": "Example Publisher",
    "issn": ["1234-5678"],
    "volume": "12",
    "issue": "3",
    "pages": {
      "first": "10",
      "last": "18",
      "article_number": null
    }
  },
  "access": {
    "is_oa": true,
    "oa_status": "gold",
    "license": "cc-by",
    "license_url": "https://creativecommons.org/licenses/by/4.0/"
  },
  "impact": {
    "citation_count": 12,
    "reference_count": 30,
    "citation_count_difference_oa_minus_crossref": 2,
    "citation_count_divergence_flag": false,
    "reference_count_difference_oa_minus_crossref": 15,
    "reference_count_divergence_flag": true
  },
  "classification": {
    "concepts": ["public health"],
    "topics": ["epidemiology"],
    "primary_topic": "Epidemiology",
    "primary_field": "Medicine",
    "primary_subfield": "Public Health",
    "primary_domain": "Health Sciences"
  },
  "funding": {
    "funder_name": ["Example Funder"],
    "funder_doi": ["10.13039/example"],
    "funder_identifier": [],
    "funder_award": []
  },
  "provenance": {
    "source_dataset": ["openalex", "crossref"],
    "source_record_id": "W123",
    "source_institution_id": null,
    "source_datestamp": "2026-07-20T00:00:00Z",
    "raw_record_available": true
  },
  "quality_flags": [
    "reference_count_divergence",
    "abstract_present"
  ]
}
```

## 5. Standard Response Envelope

List endpoints return:

```json
{
  "data": [],
  "pagination": {
    "page": 1,
    "page_size": 25,
    "total": 1234,
    "total_pages": 50
  },
  "filters": {
    "applied": {
      "year_min": 2020,
      "year_max": 2024
    }
  },
  "meta": {
    "snapshot_date": "2026-07-20",
    "dataset_stage": "final_publications"
  }
}
```

Detail endpoints return:

```json
{
  "data": {},
  "meta": {
    "snapshot_date": "2026-07-20",
    "dataset_stage": "final_publications"
  }
}
```

Error responses return:

```json
{
  "error": {
    "code": "invalid_filter",
    "message": "year_min must be less than or equal to year_max.",
    "details": {
      "field": "year_min"
    }
  }
}
```

## 6. Endpoint Inventory

### Health and Metadata

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check for deployment monitoring. |
| `GET` | `/meta` | Dataset snapshot, row counts, supported filters, and API version. |
| `GET` | `/schema/publications` | Public field dictionary for publication responses. |
| `GET` | `/limitations` | Machine-readable summary of metadata-quality limitations and required disclosures. |

### Publications

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/publications` | Search, filter, sort, and paginate publication summaries. |
| `GET` | `/publications/{publication_key}` | Full publication detail. |
| `GET` | `/publications/{publication_key}/references` | Reference-list sidecar entries where available. |
| `GET` | `/publications/{publication_key}/count-audit` | Citation/reference count source evidence where available. |
| `GET` | `/publications/{publication_key}/raw` | Raw source payload for authorized/internal deployments; disabled by default for public MVP. |

### Search and Suggestions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/search/suggest` | Autocomplete titles, authors, institutions, topics, and journals. |
| `GET` | `/search/facets` | Facet counts for the current filter context. |

### Researchers

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/researchers` | Search researcher/author-name aggregates. |
| `GET` | `/researchers/{researcher_key}` | Researcher profile aggregate by normalized display name, ORCID, or future resolved ID. |
| `GET` | `/researchers/{researcher_key}/publications` | Publication list for a researcher profile. |
| `GET` | `/researchers/{researcher_key}/coauthors` | Coauthor counts for network views. |

Researcher identity caveat: MVP researcher keys are derived from normalized
author names unless an ORCID-backed identifier is available. Responses must expose
`disambiguation_level`.

### Institutions

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/institutions` | Institution directory with publication/citation aggregates. |
| `GET` | `/institutions/{institution_key}` | Institution profile aggregate. |
| `GET` | `/institutions/{institution_key}/publications` | Publication list for an institution. |
| `GET` | `/institutions/{institution_key}/collaborators` | Institution/country collaboration edges. |
| `GET` | `/institutions/compare` | Compare 2-3 institutions by trends and headline metrics. |

Implementation note: register static routes such as `/institutions/compare`
before dynamic routes such as `/institutions/{institution_key}`.

### Topics and Fields

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/topics` | Topic directory and counts. |
| `GET` | `/topics/{topic_key}/publications` | Publications for a topic. |
| `GET` | `/fields` | Primary field/subfield counts and trends. |

### Analytics and Dashboard

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/analytics/overview` | National headline metrics for dashboard cards. |
| `GET` | `/analytics/trends` | Publication and citation trends by year. |
| `GET` | `/analytics/institutions` | Institution rankings and trend summaries. |
| `GET` | `/analytics/fields` | Field, subfield, topic, and type breakdowns. |
| `GET` | `/analytics/collaboration-network` | Nodes and edges for Cytoscape.js. |
| `GET` | `/analytics/data-quality` | Missingness, conflict, and quality-flag summary. |

### Model Serving

Initial model-serving endpoints are implemented in FastAPI under the same
`/api/v1` prefix. They expose the reusable publication text classifier trained
by the modeling pipeline.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/models` | List available served models and readiness metadata. |
| `GET` | `/models/publication-classifier` | Show classifier artifact paths, checksum state, labels, and training metrics where available. |
| `POST` | `/models/publication-classifier/predict` | Predict one publication label from `text` or `title`/`abstract`/`keywords`. |
| `POST` | `/models/publication-classifier/predict-batch` | Predict up to the configured batch limit, default 100 records. |

The prediction response includes `predicted_label`, optional `confidence`,
optional per-label `scores`, the combined serving text, echoed caller metadata,
and model checksum metadata. If the trained `.joblib` or manifest is missing,
prediction endpoints return `503 model_unavailable`.

### Exports

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/exports/publications.csv` | CSV export of filtered publication summaries. |
| `GET` | `/exports/publications.jsonl` | JSONL export of filtered publication summaries. |
| `GET` | `/exports/analytics/{name}.csv` | CSV export for supported dashboard tables. |

Export endpoints must apply the same filters and maximum-row limits as list
endpoints unless explicitly configured for internal use.

## 7. Publication List Query Parameters

| Parameter | Type | Example | Notes |
|---|---|---|---|
| `q` | string | `malaria` | Full-text search over title, abstract, authors, keywords, journal, publisher, DOI. |
| `year_min` | integer | `2016` | Inclusive. |
| `year_max` | integer | `2026` | Inclusive. |
| `type` | string, repeatable | `journal-article` | Canonical publication type. |
| `institution` | string, repeatable | `University of Colombo` | Matches resolved or source institution names. |
| `country` | string, repeatable | `LK` | ISO country code where available. |
| `field` | string, repeatable | `Medicine` | OpenAlex primary field. |
| `subfield` | string, repeatable | `Public Health` | OpenAlex primary subfield. |
| `topic` | string, repeatable | `Epidemiology` | Topic/concept filter. |
| `journal` | string, repeatable | `Ceylon Medical Journal` | Exact or normalized match. |
| `source_dataset` | string, repeatable | `openalex` | Provenance filter. |
| `is_oa` | boolean | `true` | Open-access flag. |
| `has_doi` | boolean | `true` | DOI presence filter. |
| `has_abstract` | boolean | `false` | Abstract presence filter. |
| `quality_flag` | string, repeatable | `citation_count_divergence` | Filter records with specific data-quality flags. |
| `sort` | enum | `relevance`, `year_desc`, `year_asc`, `citations_desc`, `title_asc` | Default `relevance` when `q` is present, otherwise `year_desc`. |
| `page` | integer | `1` | Minimum 1. |
| `page_size` | integer | `25` | Default 25; max 100. |
| `include_facets` | boolean | `true` | Include facet counts in response. |

Invalid combinations return `400 invalid_filter`.

## 8. Analytics Query Parameters

| Endpoint | Parameters |
|---|---|
| `/analytics/overview` | Same core filters as publications, excluding pagination. |
| `/analytics/trends` | `group_by=year|type|field|institution`, `metric=publications|citations`, core filters. |
| `/analytics/institutions` | `metric=publications|citations|oa_share`, `limit`, core filters. |
| `/analytics/fields` | `level=domain|field|subfield|topic`, `limit`, core filters. |
| `/analytics/collaboration-network` | `scope=institution|country|researcher`, `institution`, `year_min`, `year_max`, `min_weight`, `limit`. |
| `/analytics/data-quality` | `group_by=source_dataset|type|institution|year`, core filters. |

## 9. Model Serving Request Bodies

Single prediction request:

```json
{
  "title": "Public health surveillance in Sri Lanka",
  "abstract": "Study abstract.",
  "keywords": ["medicine", "public health"],
  "doi": "10.1000/example"
}
```

Alternatively, provide an already-combined `text` value. Extra top-level fields
and the `metadata` object are echoed in the prediction response metadata.

Batch prediction request:

```json
{
  "records": [
    {"text": "Bridge sensors and engineering materials.", "metadata": {"id": "1"}},
    {"title": "Clinical health system study", "abstract": "Patient care evidence."}
  ]
}
```

Runtime model settings are controlled with `RESEARCHLANKA_MODEL_PATH`,
`RESEARCHLANKA_MODEL_MANIFEST_PATH`, `RESEARCHLANKA_MODEL_LABEL_COLUMN`,
`RESEARCHLANKA_MODEL_TEXT_COLUMNS`, `RESEARCHLANKA_MODEL_VERIFY_CHECKSUM`, and
`RESEARCHLANKA_MODEL_MAX_BATCH_SIZE`.

## 10. Database Mapping

| API concept | PostgreSQL source |
|---|---|
| Publication detail/list | `final_publications` |
| Reference list | `final_publication_references` |
| Citation/reference audit | `final_publication_count_audit` |
| Raw source payload | `final_publications.raw_record` |
| Dataset load timestamp | `final_publications.loaded_at`, `final_publications.updated_at` |
| Source provenance | `source_dataset`, `source_institution_id`, `source_record_id`, `source_datestamp`, `raw_identifiers` |

MVP implementation can derive arrays by splitting semicolon-separated fields
such as `authors`, `institutions`, `topics`, `concepts`, `source_dataset`, and
`countries`. If performance or correctness becomes a problem, add materialized
entity/link tables for authors, institutions, topics, and publication sources.

## 11. Search Design

MVP search should use PostgreSQL full-text search:

- Search fields: `title`, `abstract`, `authors`, `keywords`, `journal`,
  `publisher`, `doi`, `openalex_id`.
- Ranking: PostgreSQL text rank when `q` is present; otherwise selected sort.
- Highlighting: optional for MVP; return title/abstract snippets only if
  implemented safely.

Recommended indexes for implementation:

```sql
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_final_publications_search_tsv
ON final_publications
USING gin (
    to_tsvector(
        'english',
        concat_ws(' ', title, abstract, authors, keywords, journal, publisher, doi, openalex_id)
    )
);

CREATE INDEX IF NOT EXISTS idx_final_publications_title_trgm
ON final_publications USING gin (title gin_trgm_ops);
```

Do not add these indexes until implementation benchmarking confirms the search
shape. They are design recommendations, not current migrations.

## 12. Facets

Publication search should return facet counts for:

- `publication_year`
- `type`
- `source_dataset`
- `sri_lankan_institutions`
- `countries`
- `primary_field`
- `primary_subfield`
- `topics`
- `journal`
- `is_oa`
- `quality_flags`

Facet counts should respect active filters except the facet's own filter, so the
frontend can show useful remaining options.

## 13. Quality Flags

The API should derive and expose these flags:

| Flag | Rule |
|---|---|
| `missing_doi` | `doi IS NULL`. |
| `missing_abstract` | `abstract IS NULL`. |
| `missing_institutions` | `institutions IS NULL` and `sri_lankan_institutions IS NULL`. |
| `citation_count_divergence` | `citation_count_divergence_flag = true`. |
| `reference_count_divergence` | `reference_count_divergence_flag = true`. |
| `repository_only` | `source_dataset` contains local repository evidence and no global index evidence. |
| `no_doi_local_record` | Local/repository provenance exists and DOI is missing. |
| `topic_model_source` | Topics/concepts are source/index classifications, not official national categories. |

## 14. Dashboard Contracts

### `/analytics/overview`

```json
{
  "data": {
    "publication_count": 170365,
    "citation_total": 123456,
    "average_citations": 7.25,
    "open_access_share": 0.42,
    "doi_coverage": 0.81,
    "abstract_coverage": 0.36,
    "institution_count": 35,
    "source_count": 4
  },
  "meta": {
    "snapshot_date": "2026-07-20",
    "limitations": ["observed_records_not_national_totals"]
  }
}
```

### `/analytics/trends`

```json
{
  "data": [
    {
      "year": 2020,
      "publication_count": 12000,
      "citation_total": 45000
    }
  ]
}
```

### `/analytics/collaboration-network`

```json
{
  "data": {
    "nodes": [
      {
        "id": "university-of-colombo",
        "label": "University of Colombo",
        "type": "institution",
        "publication_count": 1200,
        "first_year": 2016,
        "last_year": 2026
      }
    ],
    "edges": [
      {
        "source": "university-of-colombo",
        "target": "university-of-peradeniya",
        "source_label": "University of Colombo",
        "target_label": "University of Peradeniya",
        "weight": 42,
        "edge_type": "institution_collaboration",
        "first_year": 2018,
        "last_year": 2025
      }
    ]
  }
}
```

## 15. Security and Access

MVP is public read-only:

- No API keys for public read endpoints.
- No user-supplied SQL fragments.
- Validate all filters against allowlists.
- Cap `page_size`, export rows, and analytics `limit`.
- Add CORS only for configured frontend origins.
- Do not expose `.env`, database URLs, collector API keys, or filesystem paths.
- Public deployments should keep `/publications/{publication_key}/raw` disabled
  unless raw payload review has been approved.

Future authenticated APIs can add researcher correction flags or admin review
workflows, but those are out of scope for MVP.

## 16. Performance Targets

| Workflow | Target |
|---|---|
| Health/meta | Under 200 ms. |
| Publication list without full-text search | Under 1 second for common filters. |
| Publication search | Under 2 seconds for full corpus search. |
| Detail page | Under 500 ms excluding related-publication calls. |
| Dashboard overview | Under 1 second from cached/materialized aggregates. |
| Collaboration network | Under 3 seconds, or async/cached if large. |
| CSV export | Streamed response; cap public exports by configured max rows. |

Use materialized views for dashboard aggregates if direct SQL becomes slow.

## 17. Implementation Plan

Recommended sequence:

1. Implement database connection reuse using existing PostgreSQL configuration.
2. Add production deployment packaging around `src.api.server`.
3. Add PostgreSQL full-text indexes after benchmarking.
4. Add materialized dashboard aggregates if live aggregate queries are slow.
5. Add CSV/JSONL exports for filtered publication lists.
6. Expand the initial FastAPI model-serving app if OpenAPI becomes the primary API surface.
7. Add integration tests with a temporary PostgreSQL database or repository
    abstraction backed by fixtures.

## 18. Out of Scope for MVP

- Record ingestion through the API.
- Manual editing of canonical metadata.
- User accounts or claimed researcher profiles.
- Real-time source refresh.
- Full-text paper hosting.
- Public raw-record dumps without review.
- Semantic search and recommendations unless a tested vector/index service is
  added.

## 19. Acceptance Checklist

The API design is ready for implementation when:

- Each frontend requirement maps to at least one endpoint.
- Every list endpoint defines pagination, filters, and sorting.
- Detail responses expose provenance and quality flags.
- Analytics endpoints state their denominator and dataset snapshot.
- Error responses use a stable envelope.
- Raw payload exposure is explicitly controlled.
- The remaining implementation work is tracked separately from this design.
