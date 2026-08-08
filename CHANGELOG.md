# Changelog

## Unreleased

- Added author and institution entity disambiguation (`src/disambiguation`),
  run by `python -m src.pipeline.build_disambiguated_entities`.
  - Author clustering from ORCID, coauthor and affiliation evidence, with a
    confidence label on every cluster and conservative merge thresholds.
  - Institution resolution against the national registry via ROR, exact alias,
    address-segment and fuzzy token matching.
  - Ranked review queues for ambiguous author clusters and unresolved
    affiliations.
  - Rules and their limits documented in `docs/12_disambiguation_rules.md`.

## 0.1.0

- Added reusable `research_analytics` framework package.
- Added configuration-driven CSV, JSON, JSONL, NDJSON, and Excel imports.
- Added common publication schema, validation, cleaning, deduplication, analytics, and exports.
- Added Sri Lankan and second example-country configurations.
- Added framework CLI and Docker entrypoint.
