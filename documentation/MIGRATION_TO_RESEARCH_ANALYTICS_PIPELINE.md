# Migration To The Framework Pipeline

The project now uses `research_analytics` as the main national research
analytics framework pipeline.

## Main Sri Lanka Run

Use this command for the actual Sri Lanka national analytics workflow:

```bash
make framework-sri-lanka
```

Equivalent direct command:

```bash
python -m research_analytics.cli run-all --config configurations/sri_lanka/config.json
```

This config reads the real project dataset:

```text
data/processed/repositories_combined.csv
```

and writes national framework outputs to:

```text
outputs/sri_lanka/
```

## Legacy Scripts

The older scripts in `scripts/` remain available for collection, validation,
and one-off maintenance tasks. They are no longer the primary national
analytics pipeline.

Examples:

```text
scripts/kaggle_collect_openalex_sri_lanka.py
scripts/harvest_all.py
scripts/map_to_common_schema.py
```

These scripts can continue feeding raw or processed datasets into the framework,
but final national analytics should be produced by `research_analytics`.
