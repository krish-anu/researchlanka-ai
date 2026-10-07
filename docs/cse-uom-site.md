# UoM CSE AI site

The separate site reuses the ResearchLanka API and frontend, but it must use a
separate database containing only affiliation-verified University of Moratuwa
Department of Computer Science and Engineering publications. The frontend
profile changes presentation; it is not a security or data-scoping boundary.

## Evidence sources

- Official CSE academic staff roster: <https://uom.lk/cse/people/academic-staff>
- University of Moratuwa repository: <https://dl.lib.uom.lk/home>
- Example repository department metadata: <https://dl.lib.uom.lk/items/d2e31fb0-a252-4ca5-8aeb-58efb9848b72/full>
- OpenAlex author/work metadata: <https://docs.openalex.org/>
- Staff profiles and publication lists, including: <https://uom.lk/staff/Gamage.CD>

The checked-in roster snapshot is
`backend/data/config/cse_uom_staff.tsv`. OpenAlex, ORCID, Google Scholar, and
Scopus identifiers remain blank until a human verifies each identity. Do not
auto-accept an author from name similarity alone.

## Data sequence

1. Collect all 2016–2026 publications for every verified roster author.
2. Enrich from the UoM repository and staff publication pages.
3. Keep a candidate record when an author exactly matches a reviewed roster
   alias.
4. Set `cse_affiliation_verified=TRUE` only when the record also contains a
   University of Moratuwa affiliation. Roster-only matches remain in the
   candidate file for manual review.
5. Deduplicate by normalized DOI, then normalized title plus year.
6. Run the existing AI classifier over the verified CSE dataset.
7. Load only accepted AI records into the separate site database.

The current builder applies steps 3–5 to a ResearchLanka source dataset:

```bash
make cse-uom-dataset
```

It writes ignored, reproducible outputs under `backend/outputs/cse_uom/`:

- `cse_uom_publication_candidates_2016_2026.csv`
- `cse_uom_publications_verified_2016_2026.csv`

To create a site-ready slice from the project's already accepted AI dataset:

```bash
make cse-uom-ai-dataset
```

This writes `cse_uom_ai_publications_verified_2016_2026.csv`. For a fresh
collection, prefer classifying `cse_uom_publications_verified_2016_2026.csv`
instead of relying on the historical national AI output.

## Separate deployment

Load the verified AI CSV into a dedicated PostgreSQL database with the existing
loader, point a separate API process at that database, and start the frontend
with its CSE profile:

```bash
cd backend
CSE_UOM_DATABASE_URL=postgresql://... make cse-uom-load-site-db

cd ..
make frontend-cse-uom
```

The launcher defaults to API `http://127.0.0.1:8082/api/v1` and frontend port
`3001`. If `3001` is occupied, it selects the next available port and prints
the URL. Override either value with plain shell values when needed:

```bash
CSE_UOM_API_BASE_URL=http://127.0.0.1:8090/api/v1 \
CSE_UOM_FRONTEND_PORT=3010 \
make frontend-cse-uom
```

In production, build the frontend with `NEXT_PUBLIC_SITE_PROFILE=cse-uom` and
keep that deployment pointed only at the CSE database. A database populated
with the national dataset would make the CSE branding misleading.

## Methodological limitation

Current roster membership plus a publication-level UoM affiliation is strong
evidence, but it may not prove historical department membership for every
publication. Repository department metadata or publication-time affiliation
should take priority when available; uncertain records should remain under
manual review.
