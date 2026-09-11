"""Sri Lanka research analytics implementation.

This package holds the concrete, Sri Lanka-specific pipeline: source
collectors, dataset build stages, the PostgreSQL layer, the read-only HTTP API,
and the publication classification models.

Its sibling, ``research_analytics``, is the reusable country-agnostic framework
that this implementation is gradually being migrated onto. Both are live -- see
``docs/BACKEND_ARCHITECTURE_MAP.md`` for which to reach for, and
``docs/MIGRATION_TO_RESEARCH_ANALYTICS_PIPELINE.md`` for the migration plan.

Subpackages, in rough data-flow order::

    collectors     -> fetch records from external APIs and repositories
    preprocessing  -> flatten one source's payload into stable fields
    processing     -> JSONL to CSV, map onto the common schema
    pipeline       -> the ordered dataset build stages
    quality        -> validation, duplicate analysis, manual review
    database       -> migrations, schema, batch loading
    api            -> read-only HTTP API over the loaded corpus
    modeling       -> classifier training, embeddings, inference
    analytics      -> collaboration and co-authorship networks
    utils          -> small shared helpers

Imports within this package are absolute from the backend root
(``from src.utils.column_resolve import ...``). A bare ``from utils...`` will
not resolve.
"""
