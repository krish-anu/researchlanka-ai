# National Research Analytics Framework

## Project Objective

To design and implement a reusable, configurable framework that integrates
heterogeneous scholarly publication data and produces national-level research
analytics, with Sri Lanka used as the primary implementation and evaluation
context.

## Target Scope

This is not mainly a framework for arbitrary datasets. It is a framework for
country-level scholarly publication integration and analytics. A ministry,
research council, university consortium, or national research office should be
able to reuse the same processing code by changing:

- Country name and country code.
- Year coverage.
- National institution registry.
- Institution aliases and identifiers.
- Data-source endpoints.
- Publication types and categories.
- Column mappings.
- Deduplication thresholds.
- Enabled analytics.
- Dashboard title and labels.
- Export directory and formats.

## Architecture

```text
National configuration
        |
National data-source connectors
        |
Common national research schema
        |
Data validation and quality assessment
        |
Cleaning and standardization
        |
Deduplication and institution resolution
        |
National research exports / database schema
        |
National analytics modules
        |
API, dashboard, and standard exports
```

## National Inclusion Rule

A publication is nationally associated when at least one affiliation or
institution name resolves to an institution in the selected country's registry.
International collaborations are not excluded. They are marked separately using
`collaboration_type`.

Supported collaboration labels:

- `domestic_single_institution`
- `domestic_multi_institution`
- `international_collaboration`
- `unresolved_affiliation`
- `not_national`

## Current Implementation

- `research_analytics/config.py`: country, coverage, source, institution registry, analytics, and export configuration.
- `research_analytics/institutions.py`: national institution registry and alias resolution.
- `research_analytics/schema.py`: common national publication metadata schema.
- `research_analytics/adapters/`: OpenAlex, Crossref, OAI-PMH, REST API, CSV, JSON, Excel, and XML source adapters.
- `research_analytics/pipeline.py`: reusable national processing pipeline.
- `research_analytics/analytics.py`: productivity, citation, data-quality, institution, keyword, and collaboration summaries.
- `research_analytics/exporters.py`: standard national CSV/JSON exports.

## Standard Exports

```text
national_publications.csv
authors.csv
institutions.csv
publication_author_links.csv
publication_institution_links.csv
research_categories.csv
topics.csv
collaboration_edges.csv
data_quality_report.csv
national_analytics_summary.json
source_records.json
processing_errors.json
```

## Reusability Proof

Main demonstration:

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

Second-country proof:

```bash
python -m research_analytics.cli run-all --config configurations/example_country/config.json
```

The same collectors, schema, cleaning, deduplication, institution resolution,
analytics, and export logic run for both. Only configuration and registry files
change.

## Success Criterion

The framework shall generate publication, impact, trend, topic, and
collaboration analytics for Sri Lanka and shall demonstrate reusability on a
second national dataset without modifying the core processing and analytics
modules.
