"""Ordered dataset build stages and whole-run collection drivers.

Two kinds of module live here:

``build_*.py``
    The numbered dataset stages. Each reads one CSV and writes the next, so
    they form a chain. Every stage accepts ``--input-csv`` / ``--output-csv``
    and defaults to the canonical path under ``data/processed/common/``, which
    is why they can be run back to back with no arguments::

        python -m src.pipeline.build_institution_normalized_dataset

``harvest_*.py`` / ``collect_*.py``
    Drivers that run collectors across every configured institution or query.

The stage order and the branch points are drawn in
``docs/BACKEND_ARCHITECTURE_MAP.md``. The short version: the merge stage writes
the 76-column common schema, ``build_final_common_dataset`` narrows it to
``common_publications_final.csv``, and three independent branches leave that
file -- column filtering, institution normalization, and year filtering (which
continues on to the analysis-ready dataset used for model training).

Outputs under ``data/processed/`` are generated artifacts. Never hand-edit
them; re-run the stage that produces them.
"""
