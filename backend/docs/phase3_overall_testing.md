# Phase 3 Overall Application Testing

**Purpose:** End-to-end application quality gate covering frontend contracts, integration smoke, performance budgets, security (SQL injection, invalid parameters, data/secret exposure, HTTPS boundary, API access), concurrent load, recovery, and deploy configuration.

## How to run

From `backend/`:

```bash
# Phase 3 suite (writes structured report + security matrix)
python scripts/testing/run_phase3_overall_tests.py

# Also print a second Vitest pass from the runner (suite already bridges Vitest)
python scripts/testing/run_phase3_overall_tests.py --with-frontend

# Skip the Vitest subprocess inside pytest (static frontend contracts still run)
PHASE3_SKIP_VITEST=1 python scripts/testing/run_phase3_overall_tests.py

# Or via pytest directly
pytest tests/phase3 --phase3-report -q
```

Frontend-only:

```bash
cd frontend && npm test
```

## Automatic artifacts

Every Phase 3 run writes to `data/reports/phase3_overall_tests/`:

| File | Format | Use |
|---|---|---|
| `latest_results.csv` | CSV table | Spreadsheet / CI artifact |
| `latest_report.md` | Markdown document | Human review / thesis appendix |
| `latest_summary.json` | JSON | Machine summary (pass rate by category) |
| `latest_security_matrix.md` | Markdown matrix | Test ID \| Endpoint \| Scenario \| Expected \| Result |
| `latest_security_matrix.csv` | CSV matrix | Same columns for spreadsheets |
| `phase3_overall_<timestamp>_*.{csv,md,json}` | Timestamped copies | Historical runs |

## Test categories

| Category | Marker | What it covers |
|---|---|---|
| Frontend | `@pytest.mark.frontend` | API client resilience, rewrite proxy, auth gates, Vitest bridge |
| Integration | `@pytest.mark.integration` | Health → meta → search → detail → export smoke |
| Performance | `@pytest.mark.performance` | Latency budgets on hot read endpoints |
| Security | `@pytest.mark.security` | SQLi parameterization, invalid params, exposure, secrets, HTTPS, API access |
| Load | `@pytest.mark.load` | Concurrent read / export pressure |
| Recovery | `@pytest.mark.recovery` | DB failure, corrupt incremental status, unknown routes |
| Accessibility | `@pytest.mark.accessibility` | Structured API errors + forbidden/login routes |
| Deploy config | `@pytest.mark.deploy_config` | Compose isolation, healthchecks, required secrets |

## Security matrix columns

| Column | Meaning |
|---|---|
| Test ID | Stable ID (`SEC-001` …) |
| Endpoint | Route under `/api/v1/...` or control under test |
| Scenario | Attack or control being exercised |
| Expected | Asserted safe outcome |
| Result | `PASS` / `FAIL` / `SKIP` filled by the reporter |

## Security controls covered

1. **SQL injection** — `build_where` parameter binding; malicious `q` / path keys do not return SQL text or 500s at the service layer.
2. **Invalid parameters** — unknown filters, inverted year ranges, empty semantic `q`.
3. **Excessive data exposure** — `/publications/{key}/raw` disabled; list/detail omit `raw_record` bodies.
4. **Secret exposure** — no `NEXT_PUBLIC_AUTH_SECRET`; error bodies scanned for connection strings / tokens; Compose requires `AUTH_SECRET`.
5. **HTTPS** — `AUTH_COOKIE_SECURE` / HttpOnly / SameSite; TLS documented as ALB/Nginx boundary.
6. **API access** — AWS Compose does not publish the API port; frontend admin Next route requires `admin.pipeline.run`.

## Pass criteria for Phase 3 sign-off

1. `tests/phase3` is green (`pass_rate_pct == 100` in `latest_summary.json`), allowing only intentional skips (e.g. `PHASE3_SKIP_VITEST=1`).
2. Security matrix shows all recorded SEC-* cases PASS in `latest_security_matrix.md`.
3. Frontend Vitest is green (`cd frontend && npm test`).
4. Timestamped report files are archived with the release notes.

## Known residual risks (documented, not failing)

- Python `POST /api/v1/admin/incremental/run` has no API-key auth of its own; production relies on **private Docker network** + **Next.js capability check**. Do not publish the API port publicly without adding auth.
- Offline Phase 3 uses an in-memory fake repository; live Postgres latency/load should be validated in a staging soak when available.
- Browser E2E (Playwright) is not yet in CI; Vitest + service-layer integration are the current gate.
