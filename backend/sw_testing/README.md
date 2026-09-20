# ResearchLanka — Master Test Plan SW Testing

## Data / database integrity (12 tests)

```bash
cd backend
pytest tests/data_integrity -v
```

## Data collection and ETL (9 tests)

```bash
cd backend
pytest tests/data_collection_etl -v
```

## Automated functional testing (12 tests)

```bash
cd backend
pytest tests/functional -v
```

## AI review workflow (8 tests)

```bash
cd backend
pytest tests/ai_review -v
```

## Machine learning validation (6 tests)

```bash
cd backend
pytest tests/ml_validation -v
```

## User interface (8 tests)

```bash
cd backend
pytest tests/ui -v
```

## Performance and scalability (5 tests)

```bash
cd backend
pytest tests/performance -v
```

## Security (8 tests)

```bash
cd backend
pytest tests/security -v
```

## Failure and recovery (10 tests)

```bash
cd backend
pytest tests/failure_recovery -v
```

| ID | Test | What it simulates |
| -- | ---- | ----------------- |
| FR-01 | `test_fr01_database_unavailable_api_handles_failure_without_crashing` | DB unavailable |
| FR-02 | `test_fr02_database_recovery_operations_work_again` | DB recovery |
| FR-03 | `test_fr03_api_service_unavailable_returns_connection_error_without_corrupt_data` | API down |
| FR-04 | `test_fr04_api_service_recovery_becomes_available_again` | API recovery |
| FR-05 | `test_fr05_external_source_unavailable_etl_records_failure` | External source failure |
| FR-06 | `test_fr06_etl_pipeline_failure_does_not_silently_accept_invalid_data` | ETL/pipeline failure |
| FR-07 | `test_fr07_pipeline_recovery_rerun_succeeds_after_dependency_recovery` | Pipeline recovery |
| FR-08 | `test_fr08_invalid_api_input_returns_controlled_error_service_stays_up` | Invalid API input |
| FR-09 | `test_fr09_database_connection_recovery_subsequent_operation_succeeds` | Mid-op DB recovery |
| FR-10 | `test_fr10_application_restart_starts_successfully_and_data_remains_intact` | App restart |

## Other suites (standard pytest)

```bash
cd backend

pytest sw_testing/software_testing/test_preprocessing_unit.py -v
pytest sw_testing/software_testing/test_deployment_cicd.py -v
pytest sw_testing/software_testing/test_configuration_compatibility.py -v

pytest sw_testing/software_testing -v
```

## Layout

```
tests/data_integrity/                 # 3.1.1
tests/data_collection_etl/            # 3.1.2
tests/functional/                     # 3.1.3
tests/ai_review/                      # 3.1.4
tests/ml_validation/                  # 3.1.5
tests/ui/                             # 3.1.6
tests/performance/                    # 3.1.7
tests/security/                       # 3.1.8
tests/failure_recovery/               # 3.1.9
sw_testing/software_testing/          # remaining
sw_testing/MANUAL_EVIDENCE_GAPS.md
```
