# Institution, Affiliation and Country Standardization

Status: Complete
Covers: Week 4 tasks — standardize institution names, create institution alias mappings,
standardize affiliation information, standardize country information, identify local
collaboration records, identify international collaboration records.

## Purpose

Publication records arrive with institution names spelled many different ways, with
affiliation strings that mix departments, institutions and addresses, and — for the
majority of repository-harvested records — with no institution field at all. This stage
resolves those values onto a controlled national institution registry and derives the
collaboration fields.

No record is ever dropped. An institution that cannot be resolved is retained in
`unresolved_institutions` so the registry can be improved from evidence.

## Results

Measured on `common_publications_final.csv`, 170,365 records:

| Metric | Before | After |
|---|---|---|
| Records with an institution | 43.0% | **90.1%** |
| Records with a country | 43.0% | **90.1%** |
| Sri Lankan institution mentions resolved | 19.0% | **100.0%** (92,616 of 92,616) |
| Registry size | 11 institutions / 38 aliases | **102 institutions / 175 aliases** |
| Records typed `unresolved_affiliation` | ~57% | **4 records** |

Collaboration breakdown: local 121,696 (71.4%), international 31,797 (18.7%),
unknown 16,872 (9.9%).

### Why coverage stops at 90.1%

The remaining 9.9% is 16,824 SLJOL-only records plus 44 Crossref records. SLJOL is the
national journal-hosting platform, not an institution, so the collection source cannot
imply one. Those specific records carry no `institutions`, no `author_affiliations` and
no `countries` value in any source — there is nothing to recover. (The 8,961 SLJOL
records that *do* carry affiliation data resolve normally.)

This is a data ceiling, not an implementation gap. Raising it requires new data:
Crossref affiliation enrichment for those DOIs, or contacting SLJOL for metadata.

### Why "all institution mentions resolved" is only 50.2%

That figure counts every institution mention including foreign ones — Oxford, Melbourne,
UCL, Chinese Academy of Sciences. A *national* registry deliberately does not contain
them; they are identified by country code instead. The meaningful measure is the national
resolution rate, which is 100%. Both are reported so neither is mistaken for the other.

## Rules

### Multi-value splitting

Institution, affiliation and country fields split on **semicolon only**. Comma splitting
is never applied to these fields because institution names legitimately contain commas:

- `Eastern University, Sri Lanka` — one institution, not two
- `Ministry of Health, Nutrition and Indigenous Medicine` — one institution, not three

Free-text fields such as keywords keep the previous flexible behaviour; the split
characters are now an explicit argument to `normalize_list_like`.

### Institution matching

Matching is deterministic. A lookup key is built for every registry alias and every
incoming name, and compared exactly. No fuzzy or probabilistic matching is used, so any
resolution can be explained by pointing at the alias that produced it.

Key construction, applied identically to both sides:

1. Unicode NFKD normalization; replacement characters and curly quotes normalized.
2. Leading sub-unit segments dropped — `Department of`, `Faculty of`, `Division`, `Unit`,
   `Laboratory`, `Section`, `Chair`, `Clinic`, `Ward`, `Library` — but **only when a
   further comma-separated segment remains**. A standalone `Department of Archaeology` is
   a government body and is kept intact.
3. Trailing `, Sri Lanka` dropped.
4. Abbreviations expanded: `Univ.`→`University`, `Inst.`→`Institute`, `Natl.`→`National`,
   `Center`→`Centre`, `&`→`and`, and similar.
5. Lowercased; all non-alphanumeric runs collapsed to single spaces.

If the full key misses, resolution retries against progressively shorter comma-prefixes.
This strips address tails — `University of Peradeniya, Peradeniya 20400` resolves to
University of Peradeniya. Shortening stops before the first segment, so a name is never
reduced past its own head and `University of Oxford, Oxford` stays unresolved.

### Institution recovery, in decreasing order of confidence

| Pass | Source | Records |
|---|---|---|
| 1 | `institutions` from source metadata | 73,257 |
| 2 | `source_institution_id` — the harvesting repository | 80,233 |
| 3 | `author_affiliations`, parsed | 7 |
| — | none available | 16,868 |

Pass 2 is the largest single gain. A record harvested from the Moratuwa repository is a
Moratuwa record, so the collection code identifies the institution exactly. Platform
identifiers are excluded from this inference: `sljol`, `learn_dspace_ac_lk` and
`private_other` describe where a record was collected, not who produced it.

The pass used is recorded per record in `institution_source`, so downstream analysis can
weight or exclude the inferred values.

### Affiliation parsing

Affiliation strings are semicolon-joined institution names, sometimes carrying an address
or country tail. Parsing splits on semicolons, drops sub-unit prefixes, and extracts
country hints.

A country name is removed from the institution name **only when preceded by a comma**,
marking it as an address tail. Without that guard, an institution whose own name ends in
a country is truncated — `Rajarata University of Sri Lanka` must not become
`Rajarata University of`.

### Country standardization

Values are normalized to ISO 3166-1 alpha-2. Country *names* are recognised for a
curated list of the countries actually present plus common research partners;
unrecognised values are reported rather than silently dropped.

`XK` (Kosovo) is accepted. It is a user-assigned code outside the official ISO list, but
OpenAlex emits it and the records are real.

Countries are inferred as `LK` when a national institution resolved but no country was
present — 80,236 records.

### Collaboration classification

`collaboration_type` keeps its five existing values. `collaboration_scope` is the coarser
local/international view the work plan asks for, derived from it:

| `collaboration_type` | `collaboration_scope` |
|---|---|
| `domestic_single_institution` | `local` |
| `domestic_multi_institution` | `local` |
| `international_collaboration` | `international` |
| `unresolved_affiliation` | `unknown` |
| `not_national` | `unknown` |

## Registry

`configurations/sri_lanka/institutions.csv` — 102 institutions, 175 alias rows.

Seeded from the 101 distinct values of the `sri_lankan_institutions` column, which is
OpenAlex's own country-filtered list, so every seed value is already confirmed to be a
Sri Lankan organisation.

Identifiers are stable: an institution that already has an `LK###` identifier keeps it
across regeneration, so identifiers already written into exported datasets never change
meaning. New institutions take the next free identifier.

Curated aliases double as merge hints, which is what prevents the dataset spelling
`National Science Foundation of Sri Lanka` from becoming a second entry alongside the
existing `National Science Foundation` (LK006).

Institution types are inferred by keyword: university, hospital, research_institute,
government_body, college, company, ngo_or_association, other.

### Review items

The generator reports name pairs that nest inside one another, since that is the shape a
missed merge takes. Two were flagged and both are correct as separate entries:

- **LK001 University of Colombo / LK055 Post Graduate Institute of Medicine, University
  of Colombo** — PGIM is a distinct postgraduate institute. Setting
  `parent_institution_id` to LK001 would be reasonable; the column exists and is
  currently unused.
- **LK009 South Eastern University of Sri Lanka / LK028 Eastern University, Sri Lanka** —
  genuinely different universities.

Nesting pairs are reported, never merged automatically.

## Running

```bash
make institution-registry     # regenerate the registry, then review the CSV diff
make institution-normalize    # apply it to the merged dataset
```

Outputs, in `data/processed/common/`:

- `common_publications_final_institution_normalized.csv` — the dataset, with all input
  columns preserved plus `national_institution_ids`, `national_institutions`,
  `unresolved_institutions`, `institution_source`, `collaboration_type`,
  `collaboration_scope`
- `..._institution_normalized_summary.csv` — the metrics above
- `..._unresolved_institutions.csv` — unresolved names by frequency

## Improving coverage

Read the unresolved-institutions CSV. Anything Sri Lankan above roughly 50 mentions
belongs in the registry — add it to `CURATED_ALIASES` in
`src/pipeline/build_institution_registry.py`, regenerate, and re-run the stage. The list
is currently dominated by foreign institutions, which is expected and needs no action.

## Known limitations

- Matching is exact-key only. A misspelled institution name will not resolve.
- ROR identifiers are not populated. The `ror_id` column exists in both the registry and
  the database schema but is unused; populating it would enable matching against an
  external authority.
- Country-name recognition covers a curated list, not all of ISO 3166. Unrecognised names
  are counted in the summary so gaps are visible.
- `parent_institution_id` is unused, so postgraduate institutes and constituent campuses
  are not linked to their parent university.
