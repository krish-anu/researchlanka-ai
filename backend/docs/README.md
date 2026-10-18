# Backend Documentation Index

Use this page to choose the current document for a task. Historical audits and
superseded model reports are listed separately so that they are not mistaken
for active instructions.

## Architecture and API

- [`BACKEND_ARCHITECTURE_MAP.md`](BACKEND_ARCHITECTURE_MAP.md) - package and
  pipeline orientation.
- [`SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md`](SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md)
  - system-level data flow.
- [`API_DESIGN.md`](API_DESIGN.md) - public backend API contract.
- [`PROJECT_FUNCTIONALITY_MAP.md`](PROJECT_FUNCTIONALITY_MAP.md) - detailed
  capability-to-code map.
- [`metadata.md`](metadata.md) - publication metadata schema.

## Operating the pipeline

- [`PIPELINE_RUNBOOK.md`](PIPELINE_RUNBOOK.md) - end-to-end commands.
- [`DATA_COLLECTION.md`](DATA_COLLECTION.md) - collection sources and harvest
  procedures.
- [`normalization_and_merge.md`](normalization_and_merge.md) - normalization and
  merge rules.
- [`DATA_CLEANING_RULES.md`](DATA_CLEANING_RULES.md) - formal cleaning rules.
- [`MIGRATION_TO_RESEARCH_ANALYTICS_PIPELINE.md`](MIGRATION_TO_RESEARCH_ANALYTICS_PIPELINE.md)
  - framework migration status.
- [`NATIONAL_RESEARCH_ANALYTICS_FRAMEWORK.md`](NATIONAL_RESEARCH_ANALYTICS_FRAMEWORK.md)
  - reusable framework guide.

## AI relevance

- [`AI_RELEVANCE_MODEL.md`](AI_RELEVANCE_MODEL.md) - current production model
  source of truth.
- [`AI_RELEVANCE_PIPELINE.md`](AI_RELEVANCE_PIPELINE.md) - candidate creation,
  classification, and review flow.
- [`AI_RELEVANCE_ANNOTATION_PROTOCOL.md`](AI_RELEVANCE_ANNOTATION_PROTOCOL.md) -
  human annotation protocol.

## Metadata quality

- [`00_metadata_quality_report_index.md`](00_metadata_quality_report_index.md) -
  index for the numbered quality reports.
- [`METADATA_QUALITY_LIMITATIONS.md`](METADATA_QUALITY_LIMITATIONS.md) - current
  interpretation limitations.
- [`INSTITUTION_CODE_WALKTHROUGH.md`](INSTITUTION_CODE_WALKTHROUGH.md) -
  institution and affiliation implementation.

## Source-specific guides

- [`crossref_data_collection.md`](crossref_data_collection.md) - Crossref
  collection behavior.
- [`crossref_enrichment_pipeline.md`](crossref_enrichment_pipeline.md) -
  Crossref enrichment flow.

## Development

- [`frontend_requirements.md`](frontend_requirements.md) - backend-facing
  frontend requirements.
- [`BRANCHING_AND_COMMITS.md`](BRANCHING_AND_COMMITS.md) - contribution
  workflow.
- [`../src/api/README.md`](../src/api/README.md) - API package layout.
- [`../dagster-quickstart/README.md`](../dagster-quickstart/README.md) - Dagster
  setup.

## Historical evidence

See [`archive/`](archive/README.md) for point-in-time backend audits, framework
gap analysis, and superseded model-selection reports.
