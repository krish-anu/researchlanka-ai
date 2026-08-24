"""Small shared helpers used across the pipeline, API, and scripts.

The ``*_utils`` modules all follow one pattern, defined in
:mod:`src.utils.column_resolve`: a concept (venue, author, date) may be spread
over several overlapping columns depending on the source, so each extractor
declares a priority-ordered list of column names, takes the first populated
value, and records which column it came from for auditability.

Each extractor exposes three entry points::

    extract_x(record)              one record (dict or pandas Series)
    extract_x_by_doi(df, doi)      convenience lookup in a DataFrame
    extract_x_batch(df, size)      whole-DataFrame pass, optionally chunked

These read the **flat common schema**, not raw provider payloads -- raw
payloads are flattened first by ``src/preprocessing/``.

Modules:
    column_resolve   Shared priority-resolution helpers
    io_utils         CSV/Parquet ``load_dataset`` / ``save_dataset``
    author_utils     Author names, counts, affiliations, ORCIDs
    title_utils      Display title and normalized form for matching
    journal_utils    Venue name, ISSN, volume, issue
    publisher_utils  Publisher name and location
    date_utils       Publication date resolution and year parsing
    referece_utils   Reference and citation counts (note: filename typo)
    doi              DOI validation and normalization
    file_naming      Consistent dataset filename construction

Note: the ``*_PRIORITY`` constants currently hold a single column each, while
the module docstrings describe multi-column fallbacks. That discrepancy is an
open question -- see ``docs/BACKEND_CODE_AUDIT.md`` section 2.2.
"""
