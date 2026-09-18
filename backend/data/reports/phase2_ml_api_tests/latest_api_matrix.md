# Phase 2 API Test Matrix

- Generated (UTC): 2026-09-12T09:45:34.635304+00:00
- Cases: 26
- Passed: 26
- Failed: 0
- Skipped: 0

| Test ID | Endpoint | Scenario | Expected | Result |
|---|---|---|---|---|
| API-001 | `GET /api/v1/health` | Service health probe | status=ok and api_version present | **PASS** |
| API-002 | `GET /api/v1/meta` | Dataset metadata | publication_count and supported_filters returned | **PASS** |
| API-003 | `GET /api/v1/publications` | Default publication listing | paginated list with >=1 row | **PASS** |
| API-004 | `GET /api/v1/publications?q=Malaria` | Keyword publication search | filtered list containing malaria title | **PASS** |
| API-005 | `GET /api/v1/publications/{key}` | Publication detail by key | detail payload for doi:10.1000/test | **PASS** |
| API-006 | `GET /api/v1/publications/{key}` | Missing publication key | 404 not_found | **PASS** |
| API-007 | `GET /api/v1/publications?year_min>year_max` | Invalid year range filter | invalid_filter error | **PASS** |
| API-008 | `GET /api/v1/search/suggest?q=Malaria` | Autocomplete suggestions | suggestion list with publication type | **PASS** |
| API-009 | `GET /api/v1/search/semantic?q=malaria` | Semantic search ranking | ranked rows with semantic_score | **PASS** |
| API-010 | `GET /api/v1/search/semantic` | Semantic search without q | invalid_filter for empty query | **PASS** |
| API-011 | `GET /api/v1/search/facets` | Facet counts for current filters | facets object returned | **PASS** |
| API-012 | `GET /api/v1/topics` | Topic directory (OpenAlex fallback when NMF unavailable) | list/ranking payload or service error handled | **PASS** |
| API-013 | `GET /api/v1/fields` | Field rankings | paginated ranking rows | **PASS** |
| API-014 | `GET /api/v1/analytics/overview` | Dashboard headline metrics | overview metrics object | **PASS** |
| API-015 | `GET /api/v1/analytics/trends` | Yearly publication trends | trend points list | **PASS** |
| API-016 | `GET /api/v1/analytics/institutions` | Institution rankings | paginated ranking rows | **PASS** |
| API-017 | `GET /api/v1/analytics/fields` | Field analytics rankings | paginated ranking rows | **PASS** |
| API-018 | `GET /api/v1/analytics/collaboration-network` | Collaboration network graph | nodes/edges/summary payload | **PASS** |
| API-019 | `GET /api/v1/analytics/data-quality` | Data-quality summary | quality metrics object | **PASS** |
| API-020 | `GET /api/v1/researchers/{key}` | Researcher profile | profile aggregate | **PASS** |
| API-021 | `GET /api/v1/institutions/{key}` | Institution profile | profile aggregate | **PASS** |
| API-022 | `GET /api/v1/institutions/compare` | Compare two institutions | comparison list with 2 entries | **PASS** |
| API-023 | `GET /api/v1/publications/{key}/references` | Publication references sidecar | paginated reference rows | **PASS** |
| API-024 | `GET /api/v1/publications/{key}/related` | Related publications (semantic) | ranked related rows | **PASS** |
| API-025 | `GET /api/v1/exports/publications.csv` | CSV export of publications | text/csv bytes payload | **PASS** |
| API-026 | `GET /api/v1/unknown` | Unknown endpoint | 404 not_found | **PASS** |
