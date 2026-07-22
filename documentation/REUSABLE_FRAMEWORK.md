# Reusable National Research Analytics Framework

The reusable framework is designed for national-level research analytics. It is
separated from country-specific configuration so Sri Lanka can be the first
implementation while another national context can reuse the same pipeline.

```text
research_analytics/
  adapters/
  analytics.py
  cleaning.py
  config.py
  deduplication.py
  exporters.py
  institutions.py
  pipeline.py
  schema.py
  validation.py

configurations/
  sri_lanka/
  example_country/
  user_dataset/

examples/
  sample_publications.csv
```

The framework code contains reusable national processing logic. Country-specific
values such as country code, year range, institution registry, categories,
source settings, dashboard labels, and column mappings live in configuration
files.

## Run The Example

```bash
python -m research_analytics.cli run-all --config configurations/example_country/config.json
```

The same framework can run the Sri Lankan configuration:

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

This demonstrates that the core code does not need to change when the project changes from one country or dataset to another.

## National Objective

To design and implement a reusable, configurable framework that integrates
heterogeneous scholarly publication data and produces national-level research
analytics, with Sri Lanka used as the primary implementation and evaluation
context.

## Common Publication Schema

All datasets are mapped into:

```text
publication_id
source_name
source_record_id
doi
title
normalized_title
abstract
publication_year
publication_date
publication_type
language
journal
publisher
authors
institutions
countries
keywords
categories
topics
citation_count
open_access_status
source_url
collected_at
national_association
collaboration_type
national_institution_ids
national_institutions
resolved_institutions
unresolved_institutions
source_specific_metadata
raw_record
```

## Command-Line Workflow

```bash
research-framework source-validate --config config.json
research-framework preview --config config.json --sample-size 5
research-framework validate --config config.json
research-framework import --config config.json
research-framework clean --config config.json
research-framework deduplicate --config config.json
research-framework analyze --config config.json
research-framework run-all --config config.json
```

## Current First-Version Coverage

- Common publication schema.
- Configurable CSV, JSON, JSONL, NDJSON, and Excel import.
- Configurable column mapping.
- Source adapter interface.
- OpenAlex and OAI-PMH adapter classes.
- National institution registry and alias resolution.
- National publication inclusion metadata.
- Domestic single-institution, domestic multi-institution, international, and unresolved collaboration labels.
- Configurable cleaning rules.
- Configurable DOI and exact-title deduplication.
- Data-quality validation report.
- Source onboarding validation and preview reports.
- Adapter registry for built-in and plugin sources.
- Generic API adapter with page, offset, cursor, and next-link pagination support.
- Pagination helper classes for page, offset, cursor, next-link, and resumption-token strategies.
- Field-aware analytics with skipped-analysis messages.
- CSV and JSON export files.
- Standard national exports such as `national_publications.csv`,
  `authors.csv`, `institutions.csv`, `collaboration_edges.csv`,
  `data_quality_report.csv`, and `national_analytics_summary.json`.
- Sri Lankan and second example-country configurations.
- User templates for mappings and aliases.

## Adding A New Dataset Source

For a normal file source, users only edit configuration:

```json
{
  "source": {
    "name": "new_university_repository",
    "type": "csv",
    "path": "data/new_repository.csv"
  },
  "column_mapping": {
    "paper_name": "title",
    "researcher_names": "authors",
    "campus": "institutions",
    "published": "publication_year",
    "reference_count": "citation_count"
  }
}
```

Before importing everything, run:

```bash
python -m research_analytics.cli source-validate --config config.json
python -m research_analytics.cli preview --config config.json --sample-size 5
```

For a REST API, start from:

```text
configurations/user_dataset/api_source_template.json
```

For a complex source that cannot be configured, add a plugin under:

```text
plugins/example_repository/
```

The core pipeline still calls only the `SourceAdapter` interface, so cleaning,
deduplication, analytics, exports, API, and dashboard layers do not need to be
rewritten for a new source.
