# Singapore Pipeline Checklist

This project now includes a Singapore framework scaffold:

- `configurations/singapore/config.json`
- `configurations/singapore/institutions.csv`

The first Singapore source is OpenAlex, filtered by Singapore affiliation country
code `SG`. The config uses `max_records: 100` so the first test run is quick.

## 1. Confirm the Local Framework

Run the offline sample first. This checks transform, validation, cleaning,
deduplication, analytics, and exports without internet access.

```bash
python -m research_analytics.cli run-all --config configurations/example_country/config.json
```

Expected result:

```text
Run complete: 4 raw, 4 cleaned, 3 deduplicated.
```

## 2. Preview Singapore OpenAlex Data

Run this on a machine with internet access:

```bash
python -m research_analytics.cli preview --config configurations/singapore/config.json --sample-size 5
```

If this works, run the full framework pipeline:

```bash
python -m research_analytics.cli run-all --config configurations/singapore/config.json
```

Outputs are written to:

```text
outputs/singapore/
```

Important output files:

- `national_publications.csv`
- `cleaned_publications.csv`
- `deduplicated_publications.csv`
- `authors.csv`
- `institutions.csv`
- `collaboration_edges.csv`
- `data_quality_report.csv`
- `analytics_summary.json`
- `processing_report.json`

## 3. Scale Beyond the Test Limit

After the `max_records: 100` test succeeds, edit:

```text
configurations/singapore/config.json
```

Change:

```json
"max_records": 100
```

to either a larger number or `null` for a full OpenAlex run.

Use an email address for polite OpenAlex API usage:

```json
"email": "your_email@example.com"
```

## 4. What Is Already Covered

The Singapore OpenAlex framework run covers:

- collection from OpenAlex
- transform to the project standard publication schema
- validation
- cleaning
- institution/country context resolution
- DOI/title deduplication
- analytics
- CSV and JSON exports

This is the quickest full-pipeline test from source collection to analytics.

## 5. Crossref and Repository Sources

The reusable framework currently runs one active source at a time. If you need a
multi-source Singapore dataset like the Sri Lanka final dataset, use this route:

1. Collect/export OpenAlex Singapore records.
2. Collect/export Crossref Singapore records in a separate run or script.
3. Collect/export Singapore repository records after creating a Singapore
   repository registry.
4. Normalize all source CSVs to the expected common fields.
5. Merge/deduplicate them with a common merge script.
6. Run the framework analytics on the merged CSV.

For repository collection, create Singapore entries in a repository registry
with these fields:

- `id`
- `name`
- `oai_endpoint`
- `rest_api_endpoint`
- `browse_url`
- `status`
- `phase`
- `harvest_route`
- `endpoint_verified_live`
- `ssl_verify_failed`
- `notes`

Then run the same repository workflow:

```bash
python scripts/validate_repositories.py
python scripts/harvest_oai.py --id <id>
python scripts/harvest_dspace_rest.py --id <id>
python scripts/harvest_html_meta.py --id <id>
python scripts/map_to_common_schema.py --all
python scripts/convert_repositories_jsonl_to_csv.py
python scripts/validate_harvested_data.py
```

Use only the route that actually works for each repository: OAI-PMH first, REST
second, HTML metadata only as a last resort.

## 6. Final Merge Pattern

The existing final merge script is:

```bash
python scripts/kaggle_merge_common_dataset.py
```

It is currently shaped around the Sri Lanka Drive files:

- `crossref_clean_2016_2026_enriched.csv`
- `openalex_sri_lanka_works.csv`
- `repositories_combined.csv`
- `sljol.csv`

For Singapore, either rename/prepare equivalent files with the same schemas, or
adapt the expected filenames and source-specific normalization in that script.

After producing one merged Singapore CSV, point a framework config at that file
with `source.type: csv` and run:

```bash
python -m research_analytics.cli run-all --config configurations/singapore/config.json
```

Update the config input/source path first if you switch from OpenAlex API mode
to merged CSV mode.
