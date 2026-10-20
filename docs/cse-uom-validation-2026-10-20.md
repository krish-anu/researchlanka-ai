# UoM CSE AI Dataset Validation — 2026-10-20

## Scope

This report records the CSE-specific validation run against the current
24-person official academic-staff roster. It validates author matching,
publication-level University of Moratuwa evidence, reviewed DOI corrections,
deduplication, and a fresh OpenAlex collection for verified staff identities.
It is not a claim that every bibliographic field has been independently checked
with every publisher.

## Result

| Decision | Records |
| --- | ---: |
| Fresh OpenAlex staff works collected | 1,010 |
| Affiliation-verified distinct CSE publications | 844 |
| Final accepted AI publications | 481 |
| Newly fetched AI-review records withheld from the site | 133 |
| Affiliation candidates withheld from the site | 180 |
| Rejected reviewed attribution | 1 |

The reproducible outputs are:

- `backend/outputs/cse_uom/cse_uom_ai_publications_verified_2016_2026.csv`
- `backend/outputs/cse_uom/cse_uom_ai_validation_audit.csv`
- `backend/outputs/cse_uom/cse_uom_ai_validation_summary.json`
- `backend/outputs/cse_uom/cse_uom_openalex_staff_publications_manifest.json`

The department handover package is under
`deliverables/cse-uom-website-data-2026-10-20/`.

## Confirmed Corrections

1. DOI `10.1109/mercon63886.2024.10688929` was rejected as a Prof. Shantha
   Fernando attribution. The author is M. P. S. Fernando of UoM Electrical
   Engineering, not M.S.D. Fernando of CSE.
2. DOI `10.21833/ijaas.2020.07.007` was corrected to retain all three authors:
   Subhash Ariyadasa, Subha Fernando, and Shantha Fernando. The publisher lists
   Shantha Fernando with UoM CSE.
3. DOI `10.66543/3084-858X.1109` was restored from reviewed publisher metadata.
   The publisher lists Indika Perera and Shantha Fernando with UoM CSE.

The evidence URLs and reasons are stored in
`backend/data/config/cse_uom_publication_corrections.tsv` and copied into every
affected audit row.

## Records Still Requiring Human Review

- `10.1007/978-3-031-23793-5_23` — initials-only Uthayasanker match.
- `10.1109/SCSE59836.2023.10215041` — Indika Perera name match without UoM
  publication affiliation.
- `10.1007/978-3-031-76473-8_10` — initials-only R.M.S. Rathnayake match.
- `10.31705/ERU.2025.26` — initials-only S.J. Sooriyaarachchi match.

These records are excluded from the verified site dataset until supporting
identity and publication-time affiliation evidence is recorded.

## Matching Policy

- A full-name roster alias plus publication-level UoM affiliation may be
  verified.
- A matching verified identifier such as ORCID plus publication-level UoM
  affiliation may be verified.
- Initial-only aliases are never auto-verified.
- Reviewed DOI-level corrections may explicitly include or exclude a staff
  attribution and must contain a reason and evidence URL.
- `REVIEW` and `REJECT` rows do not enter the verified site dataset.

## Remaining Limitation

The run establishes conservative CSE attribution for the site slice. OpenAlex
identities were verified for 22 of the 24 current staff members. Google Scholar
blocked automated publication-page retrieval with HTTP 403/429, and 133 fresh
records remain in the AI manual-review band. Those records and the affiliation
review queue must be resolved with staff confirmation before making a formal
claim of exhaustive recall. The publishable dataset excludes every unresolved
attribution.
