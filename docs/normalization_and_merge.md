# Dataset Merge Rules

The common-dataset merge uses an explicit, configurable field-level source
policy. Sources are not treated as equal, and no external source is treated as
absolute truth for every field.

Default role model:

- OpenAlex: primary discovery and analytics backbone.
- Crossref: DOI-backed and publisher-deposited metadata evidence.
- Local repositories / SLJOL: national coverage, local-only records, and provenance.
- ResearchLanka output tables: final operational canonical dataset for the app.

The built-in field policy lives in `scripts/processing/kaggle_merge_common_dataset.py` and
can be overridden with:

```bash
python scripts/processing/kaggle_merge_common_dataset.py --field-source-policy policy.json
```

Example override:

```json
{
  "title": ["openalex", "crossref", "sljol", "repositories_combined"],
  "abstract": ["crossref", "repositories_combined", "sljol", "openalex"]
}
```

Merge behavior:

- Scalar fields choose the first non-empty value from the configured source order.
- Rows from the same source are tie-broken by record completeness.
- Multi-value fields retain combined evidence with duplicate values removed.
- Source-specific counts are moved to `publication_count_audit.csv`.
- Conflicting normalized values are recorded in `common_publications_merge_log.csv`.

Selected default field policy:

| Field group | Default policy |
|---|---|
| DOI | Crossref -> OpenAlex -> SLJOL -> repositories |
| Title / year / type | Crossref -> OpenAlex -> SLJOL -> repositories |
| Abstract | Crossref -> repositories -> SLJOL -> OpenAlex |
| OA status / topics | OpenAlex |
| Citation count | OpenAlex, with Crossref retained in count audit |
| Reference count | Crossref, with OpenAlex retained in count audit |
| Funding / event / license | Crossref -> OpenAlex -> local sources |
| Local provenance | Local source only / unioned provenance fields |
