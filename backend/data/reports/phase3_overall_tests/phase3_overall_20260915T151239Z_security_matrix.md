# Phase 3 Security Test Matrix

- Generated (UTC): 2026-09-15T15:12:39.544711+00:00
- Cases: 10
- Passed: 10
- Failed: 0
- Skipped: 0

| Test ID | Endpoint | Scenario | Expected | Result |
|---|---|---|---|---|
| SEC-001 | `GET /api/v1/publications` | SQL injection via q parameter | Safe filter handling; no 500/SQL leak | **PASS** |
| SEC-002 | `GET /api/v1/publications` | Stacked-query injection attempt | Safe filter handling; no 500/SQL leak | **PASS** |
| SEC-003 | `GET /api/v1/search/suggest` | SQL injection via suggest q | Safe suggestions or validation error | **PASS** |
| SEC-004 | `GET /api/v1/publications/{key}` | Path-key injection attempt | 404/validation; no SQL leak | **PASS** |
| SEC-005 | `GET /api/v1/publications` | Invalid year range | invalid_filter error | **PASS** |
| SEC-006 | `GET /api/v1/publications` | Unknown query parameter | invalid_query_parameter error | **PASS** |
| SEC-007 | `GET /api/v1/publications` | Oversized page_size | clamped/validated list response or invalid_filter | **PASS** |
| SEC-008 | `GET /api/v1/publications/{key}/raw` | Raw record endpoint disabled | disabled_endpoint | **PASS** |
| SEC-009 | `GET /api/v1/publications` | List response omits raw_record body | No raw_record / secret_token in list payload | **PASS** |
| SEC-010 | `GET /api/v1/search/semantic` | Empty semantic query rejected | invalid_filter | **PASS** |
