# National Research Analytics Framework

## Project Objective

To design and implement a Sri Lanka national-level framework that integrates
heterogeneous scholarly publication data and produces national research
analytics.

## Target Scope

This is a Sri Lanka national scholarly publication integration and analytics
framework. Its configuration captures:

- Sri Lanka country name and country code.
- Year coverage.
- Sri Lanka institution registry.
- Institution aliases and identifiers.
- Data-source endpoints.
- Publication types and categories.
- Column mappings.
- Deduplication thresholds.
- Enabled analytics.
- Sri Lanka dashboard title and labels.
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

- `research_analytics/config.py`: Sri Lanka coverage, source, institution registry, analytics, and export configuration.
- `research_analytics/institutions.py`: national institution registry and alias resolution.
- `research_analytics/schema.py`: common national publication metadata schema.
- `research_analytics/adapters/`: OpenAlex, Crossref, OAI-PMH, REST API, CSV, JSON, Excel, and XML source adapters.
- `research_analytics/pipeline.py`: Sri Lanka national processing pipeline.
- `research_analytics/analytics.py`: productivity, citation, data-quality, institution, keyword, and collaboration summaries.
- `research_analytics/exporters.py`: standard national CSV/JSON exports.
- `docs/API_DESIGN.md`: read-only API contract for search, profile pages, dashboards, networks, exports, and quality disclosures.

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

## Main Sri Lanka Run

Run the Sri Lanka national pipeline:

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

## Success Criterion

The framework shall generate publication, impact, trend, topic, and
collaboration analytics for Sri Lanka from the configured national data
sources.
