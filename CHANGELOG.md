# Changelog

## Unreleased

- Added author profiles: author sign-up with administrator approval, publication
  claims by listed author, verified public profiles at `/authors/<slug>`,
  live-editable bio and links, administrator-reviewed publication corrections
  that survive pipeline reloads, and administrator-reviewed new publications
  checked by the AI relevance model before entering the dataset.
- Added migration `016_create_author_profiles.sql` and the
  `refresh_public_publication_views()` function.
- `--retire-stale` no longer retires author-submitted publications; `--reset`
  refuses to run while author profiles or contributions exist.
- New publications list every author with their institution for that paper,
  can link authors to existing names or verified profiles, and are filed under
  a field/subfield (author, OpenAlex, or the field classifier; admin can
  override).
- Authors can merge every printed spelling of their name into one profile, keep
  an affiliation history, and remove publications attributed to them by
  mistake. Migration `017_add_author_affiliation_history.sql`.

## 0.1.0

- Added reusable `research_analytics` framework package.
- Added configuration-driven CSV, JSON, JSONL, NDJSON, and Excel imports.
- Added common publication schema, validation, cleaning, deduplication, analytics, and exports.
- Added Sri Lankan and second example-country configurations.
- Added framework CLI and Docker entrypoint.
