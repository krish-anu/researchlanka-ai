# CSE UoM AI publication website dataset

Prepared on 2026-10-20 for the University of Moratuwa Department of Computer
Science and Engineering website.

## Publishable file

`cse_uom_ai_publications_final_2016_2026.csv` contains 481 distinct,
affiliation-verified AI publications. Every row has
`cse_affiliation_verified=TRUE` and `ai_classification_label=AI`.

The file combines 299 previously accepted AI records with 182 new
high-confidence AI records from a fresh OpenAlex staff-author collection.
There are no duplicate DOI/title-year keys and no blank titles. Records without
a DOI are retained because DOI coverage is not complete for repository and
conference publications.

## Internal review file

`cse_uom_ai_manual_review.csv` contains 133 newly fetched publications in the
AI model's review band. These are excluded from the publishable file until a
human confirms their AI relevance.

## Collection scope

- Official CSE roster checked: 24 current academic staff.
- Verified OpenAlex identities: 22 staff.
- Fresh OpenAlex works fetched for 2016-2026: 1,010.
- CSE publications with verified UoM affiliation after deduplication: 844.
- Final accepted AI publications: 481.
- Publication years: 2016 through 2026.

OpenAlex ID and ORCID matching is combined with publication-level University
of Moratuwa affiliation evidence. Initial-only name matches are never accepted
by themselves.

## Known limits

Google Scholar blocked automated publication-page retrieval with HTTP 403/429,
so Scholar could not be independently bulk-harvested. The official UoM Scholar
directory was used as identity evidence where available. Two current staff
members do not yet have a trustworthy OpenAlex identity in the roster; official
full-name/UoM-affiliation fallback matching is used where possible.

The 133-record AI review queue and the separate affiliation review queue should
be resolved with staff confirmation for a formal claim of exhaustive recall.
The publishable file is intentionally conservative and contains no unresolved
attributions.

## Website loading

From `backend/`, set the dedicated CSE database URL and load the publishable
file:

```bash
CSE_UOM_DATABASE_URL=postgresql://... \
make cse-uom-load-site-db \
  CSE_UOM_AI_VERIFIED=../deliverables/cse-uom-website-data-2026-10-20/cse_uom_ai_publications_final_2016_2026.csv
```

Use a database dedicated to the CSE site; do not point the CSE-branded frontend
at the national ResearchLanka database.

