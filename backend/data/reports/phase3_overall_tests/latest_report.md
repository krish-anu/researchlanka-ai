# Phase 3 — Overall Application Test Report

- **Suite:** `phase3_overall`
- **Generated (UTC):** 2026-09-15T15:12:39.544711+00:00
- **Total tests:** 58
- **Passed:** 57
- **Failed:** 1
- **Skipped:** 0
- **Pass rate:** 98.28%

## Results by category

| Category | Total | Passed | Failed | Skipped | Pass rate |
|---|---:|---:|---:|---:|---:|
| accessibility | 2 | 2 | 0 | 0 | 100.0% |
| deploy_config | 3 | 3 | 0 | 0 | 100.0% |
| frontend | 5 | 4 | 1 | 0 | 80.0% |
| integration | 5 | 5 | 0 | 0 | 100.0% |
| load | 3 | 3 | 0 | 0 | 100.0% |
| performance | 6 | 6 | 0 | 0 | 100.0% |
| recovery | 6 | 6 | 0 | 0 | 100.0% |
| security | 28 | 28 | 0 | 0 | 100.0% |

## Coverage intent (Phase 3)

| Area | What is validated |
|---|---|
| Frontend | Auth gates, cookie flags, API client resilience, rewrite/proxy |
| Integration | Health → meta → search → detail service smoke flow |
| Performance | Latency budgets on hot read endpoints |
| Security | SQLi parameterization, invalid params, exposure, secrets, HTTPS, API access |
| Load | Concurrent read pressure on service layer |
| Recovery | DB/API failure and corrupt admin status handling |
| Deploy config | Compose isolation, seed accounts, TLS boundary |

## Detailed results

| Category | Outcome | Duration (s) | Test |
|---|---|---:|---|
| accessibility | passed | 0.000 | `test_api_error_bodies_are_structured_for_ui_panels` |
| accessibility | passed | 0.000 | `test_frontend_forbidden_and_login_routes_exist` |
| deploy_config | passed | 0.000 | `test_compose_restart_and_healthchecks_present` |
| deploy_config | passed | 0.000 | `test_database_password_required_in_compose` |
| deploy_config | passed | 0.000 | `test_frontend_only_public_port_in_aws_compose` |
| frontend | failed | 3.930 | `test_vitest_suite_passes` |
| frontend | passed | 0.000 | `test_api_client_uses_server_side_base_url_and_timeout` |
| frontend | passed | 0.000 | `test_frontend_permissions_gate_admin_pipeline` |
| frontend | passed | 0.000 | `test_next_rewrite_proxies_api_v1_same_origin` |
| frontend | passed | 0.000 | `test_package_json_exposes_test_script` |
| integration | passed | 0.000 | `test_export_csv_integration` |
| integration | passed | 4.318 | `test_health_meta_list_detail_flow` |
| integration | passed | 0.000 | `test_missing_resources_are_404` |
| integration | passed | 0.000 | `test_researcher_and_institution_profiles` |
| integration | passed | 0.000 | `test_search_suggest_facets_and_analytics_chain` |
| load | passed | 0.005 | `test_concurrent_export_reads_do_not_raise` |
| load | passed | 0.008 | `test_concurrent_health_checks` |
| load | passed | 0.007 | `test_concurrent_mixed_read_workload` |
| performance | passed | 0.000 | `test_analytics_overview_latency_budget` |
| performance | passed | 0.000 | `test_collaboration_network_latency_budget` |
| performance | passed | 0.000 | `test_health_latency_budget` |
| performance | passed | 0.000 | `test_publication_list_latency_budget` |
| performance | passed | 0.000 | `test_semantic_search_latency_budget` |
| performance | passed | 0.000 | `test_suggest_latency_budget` |
| recovery | passed | 0.000 | `test_corrupt_incremental_status_raises_api_error` |
| recovery | passed | 0.000 | `test_health_fails_closed_when_database_unreachable` |
| recovery | passed | 0.000 | `test_invalid_json_array_status_raises` |
| recovery | passed | 0.000 | `test_list_publications_surfaces_repository_failure_without_secret_url` |
| recovery | passed | 0.000 | `test_missing_incremental_status_file_returns_idle` |
| recovery | passed | 0.000 | `test_unknown_endpoint_recovers_with_not_found` |
| security | passed | 0.000 | `test_build_where_never_embeds_sqli_literals[" OR ""="]` |
| security | passed | 0.000 | `test_build_where_never_embeds_sqli_literals[' OR 1=1 --]` |
| security | passed | 0.000 | `test_build_where_never_embeds_sqli_literals[1 UNION SELECT password FROM users--]` |
| security | passed | 0.000 | `test_build_where_never_embeds_sqli_literals[1; DROP TABLE final_publications;--]` |
| security | passed | 0.000 | `test_build_where_never_embeds_sqli_literals[malaria') OR ('1'='1]` |
| security | passed | 0.000 | `test_compose_disables_seed_test_accounts_and_requires_auth_secret` |
| security | passed | 0.001 | `test_compose_does_not_publish_api_port` |
| security | passed | 0.000 | `test_error_payload_shape_avoids_internal_paths` |
| security | passed | 0.000 | `test_frontend_admin_route_requires_capability` |
| security | passed | 0.000 | `test_frontend_middleware_protects_admin_and_account` |
| security | passed | 0.001 | `test_https_boundary_documented_for_deploy` |
| security | passed | 0.000 | `test_no_auth_secret_in_next_public_env_example` |
| security | passed | 0.000 | `test_publication_detail_does_not_dump_raw_record_blob` |
| security | passed | 0.000 | `test_publication_summary_does_not_expose_raw_record` |
| security | passed | 0.000 | `test_python_admin_write_surface_is_post_only_and_conflict_aware` |
| security | passed | 0.000 | `test_quote_identifier_escapes_embedded_quotes` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-001]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-002]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-003]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-004]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-005]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-006]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-007]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-008]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-009]` |
| security | passed | 0.000 | `test_security_matrix_case[SEC-010]` |
| security | passed | 0.000 | `test_session_cookie_defaults_http_only_and_secure_in_production` |
| security | passed | 0.000 | `test_sql_build_where_parameterizes_user_input` |

## Failures

### `tests/phase3/test_phase3_frontend.py::test_vitest_suite_passes`

- Category: `frontend`
- Message: `def test_vitest_suite_passes():         """Run the frontend unit suite and fail Phase 3 if Vitest is red."""         if os.environ.get("PHASE3_SKIP_VITEST") == "1":             pytest.skip("PHASE3_SKIP_VITEST=1")         if not FRONTEND_ROOT.exists():             pytest.skip("frontend package missing")         npm = shutil.which("npm")         if npm is None:             pytest.skip("npm not available")              completed = subprocess.run(             [npm, "test", "--silent"],             cwd=FRONTEND_ROOT,             capture_output=True,             text=True,             check=False,         )         if completed.returncode != 0: >           pytest.fail(                 "Frontend Vitest failed:\n"                 + (completed.stdout[-2000:] if completed.stdout else "")            `


## Security matrix summary

- Cases: 10
- Passed: 10
- Failed: 0
- Skipped: 0

Full matrix: `phase3_overall_20260915T151239Z_security_matrix.md` / `phase3_overall_20260915T151239Z_security_matrix.csv`

## Artifacts

- CSV table: `phase3_overall_20260915T151239Z_results.csv`
- JSON summary: `phase3_overall_20260915T151239Z_summary.json`
- This report: `phase3_overall_20260915T151239Z_report.md`
