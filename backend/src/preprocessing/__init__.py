"""Per-source payload normalization.

Each module here takes one source's nested API response and flattens it to the
stable field set that the rest of the pipeline expects. This is the only place
that should know the shape of a particular provider's JSON.

Keep these functions pure and side-effect free: they take a record, they return
a record. Anything that touches the network belongs in ``src/collectors/``;
anything that reads or writes files belongs in ``src/processing/`` or
``src/pipeline/``.

Modules:
    crossref_normalizer   Crossref work -> flat field set (``reduce_work``)
    openalex_normalizer   OpenAlex work -> flat field set
"""
