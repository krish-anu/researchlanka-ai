"""Source collectors -- everything that talks to an external system.

Collectors own network access and pagination only; they never orchestrate a
run. Command-line entry points live in ``scripts/`` and ``src/pipeline/`` and
call into these classes rather than duplicating request logic.

Every collector follows the same shape so they stay interchangeable::

    fetch_*()   request exactly one API resource or page
    iter_*()    handle pagination, yield records one at a time
    total_*()   only where the source exposes a reliable count

Shared retry/backoff session behaviour lives in :mod:`src.collectors.http` and
should be used by all of them. Source-specific field flattening belongs in
``src/preprocessing/``, not here -- a collector yields either the raw payload
or a thin normalization of it, and nothing more.

Modules:
    oai_pmh_collector      OAI-PMH repositories (most university repositories)
    dspace_rest_collector  DSpace REST, where OAI-PMH coverage is incomplete
    openalex_collector     OpenAlex works API
    crossref_collector     Crossref by affiliation, by DOI, and by DOI prefix
    html_meta_collector    HTML meta-tag scraping where no API exists
    sitemap_collector      Sitemap URL discovery
    http                   Shared retrying session factory
    repository_registry    Which institution is harvested by which method
    schema_mapping         Source field -> common schema field
"""
