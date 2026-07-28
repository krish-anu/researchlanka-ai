# Columns 26-50: Final Dataset Decisions

**Dataset reviewed:** `data/processed/common/common_publications_deduplicated.csv`
**Shape reviewed:** 170,365 rows x 76 columns
**Columns reviewed:** columns 26-50, from `author_orcids` through `license_url`
**Purpose:** decide which of these 25 columns should be kept, merged, harmonized, or dropped, completing the schema review started in [07_last_26_columns_final_dataset_decisions.md](07_last_26_columns_final_dataset_decisions.md).

Reproduce every figure below with:

```bash
python scripts/profile_common_dataset.py --report-dir data/reports/profile
```

## Executive Decision

Keep **19** columns and drop **6**. Three of the drops are lossless; three are judgement calls on sparsity.

| Decision | Columns |
|---|---|
| Drop - exact duplicate of `journal` | `container_title`, `source_name` |
| Drop - derivable and less complete than the pair it duplicates | `page` |
| Drop - single constant value, zero information | `rights` |
| Drop - too sparse to analyse | `editors`, `publisher_location` |
| Keep, but harmonize before analysis | `language`, `publisher`, `journal` |
| Keep as-is | `author_orcids`, `sri_lankan_authors`, `contributors`, `institutions`, `sri_lankan_institutions`, `countries`, `source_type`, `issn`, `issn_l`, `volume`, `issue`, `first_page`, `last_page`, `article_number`, `license`, `license_url` |

## Evidence Summary

All figures are against 170,365 total rows.

| Pos | Column | Present | Coverage | Missing | Missing % | Distinct | Multi-value | Decision |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 26 | `author_orcids` | 21,659 | 12.71% | 148,706 | 87.29% | 16,565 | 50.7% | Keep - sparse but high value |
| 27 | `sri_lankan_authors` | 73,256 | 43.00% | 97,109 | 57.00% | 52,713 | 60.1% | Keep + audit |
| 28 | `contributors` | 9,771 | 5.74% | 160,594 | 94.26% | 2,341 | 39.8% | Keep - repository provenance |
| 29 | `editors` | 1,201 | 0.70% | 169,164 | 99.30% | 1,031 | 12.8% | **Drop** |
| 30 | `institutions` | 73,257 | 43.00% | 97,108 | 57.00% | 26,211 | 56.3% | Keep |
| 31 | `sri_lankan_institutions` | 73,257 | 43.00% | 97,108 | 57.00% | 3,445 | 20.1% | Keep |
| 32 | `countries` | 73,257 | 43.00% | 97,108 | 57.00% | 6,260 | 43.1% | Keep |
| 33 | `publisher` | 143,621 | 84.30% | 26,744 | 15.70% | 6,246 | 0.2% | Keep + harmonize |
| 34 | `publisher_location` | 3,632 | 2.13% | 166,733 | 97.87% | 68 | 0.0% | **Drop** |
| 35 | `journal` | 88,403 | 51.89% | 81,962 | 48.11% | 14,509 | 0.4% | Keep + harmonize |
| 36 | `container_title` | 88,403 | 51.89% | 81,962 | 48.11% | 14,509 | 0.4% | **Drop - exact duplicate** |
| 37 | `source_name` | 88,403 | 51.89% | 81,962 | 48.11% | 14,509 | 0.4% | **Drop - exact duplicate** |
| 38 | `source_type` | 160,684 | 94.32% | 9,681 | 5.68% | 5 | 0.0% | Keep - already clean |
| 39 | `issn` | 52,166 | 30.62% | 118,199 | 69.38% | 11,647 | 49.7% | Keep |
| 40 | `issn_l` | 52,166 | 30.62% | 118,199 | 69.38% | 11,384 | 0.1% | Keep - canonical join key |
| 41 | `volume` | 48,175 | 28.28% | 122,190 | 71.72% | 1,224 | 0.0% | Keep |
| 42 | `issue` | 38,148 | 22.39% | 132,217 | 77.61% | 558 | 0.0% | Keep |
| 43 | `page` | 50,706 | 29.76% | 119,659 | 70.24% | 23,740 | 0.0% | **Drop - derivable** |
| 44 | `first_page` | 55,472 | 32.56% | 114,893 | 67.44% | 11,869 | 0.0% | Keep |
| 45 | `last_page` | 55,431 | 32.54% | 114,934 | 67.46% | 11,816 | 0.0% | Keep |
| 46 | `article_number` | 10,150 | 5.96% | 160,215 | 94.04% | 7,626 | 0.0% | Keep - flagged unreliable |
| 47 | `language` | 131,389 | 77.12% | 38,976 | 22.88% | 55 | 0.0% | Keep + harmonize |
| 48 | `rights` | 503 | 0.30% | 169,862 | 99.70% | **1** | 0.0% | **Drop - constant** |
| 49 | `license` | 34,871 | 20.47% | 135,494 | 79.53% | 9 | 0.0% | Keep |
| 50 | `license_url` | 40,275 | 23.64% | 130,090 | 76.36% | 388 | 43.2% | Keep + normalize URLs |

## Per-Column Reference

Source percentages below are the share of that source's own rows carrying the field.

### Author and contributor fields (26-29)

**[26] `author_orcids`** - present 21,659 (12.71%), missing 148,706 (87.29%), 16,565 distinct, 50.7% multi-valued. OpenAlex 29.6%, Crossref 15.4%.
Persistent researcher identifiers, and the only field in this block that unambiguously disambiguates authors - name strings collide constantly, ORCIDs do not. Low coverage reflects real-world ORCID adoption, not a pipeline defect.
**Keep.** Anchor author-disambiguation work here and treat the 87% without an ORCID as requiring name matching with explicit uncertainty.

**[27] `sri_lankan_authors`** - present 73,256 (43.00%), missing 97,109 (57.00%), 52,713 distinct, 60.1% multi-valued. OpenAlex 100%, Crossref 29.5%.
OpenAlex-flagged Sri Lankan authors. Equals the full `authors` list in 19.8% of rows, identifying wholly domestic author teams.
**Keep, but audit first.** The most frequent value is `LUNCHANAWAT NIMMAHNRATANAKUL` (397 rows), a Thai name, which also appears as `NIMMAHNRATANAKUL, LUNCHANAWAT` (143). The field carries both false positives and inconsistent name formatting.

**[28] `contributors`** - present 9,771 (5.74%), missing 160,594 (94.26%), 2,341 distinct, 39.8% multi-valued. Repositories 11.1%.
Non-primary contributors from repository records: supervisors, editors, corporate bodies. Format is `Surname, Initials`, inconsistent with `authors`.
**Keep, low priority.** The only trace of supervisory relationships in theses. Do not merge into `authors` - different semantics.

**[29] `editors`** - present 1,201 (0.70%), missing 169,164 (99.30%), 1,031 distinct. OpenAlex 1.6%.
Book and proceedings editors. Contaminated: `Auctores Publishing LLC` is a publisher, not an editor.
**Drop.** Recoverable from Crossref if a book-chapter study is commissioned.

### Affiliation fields (30-32)

**[30] `institutions`** - present 73,257 (43.00%), missing 97,108 (57.00%), 26,211 distinct, 56.3% multi-valued. OpenAlex 100% exclusively.
All affiliations including foreign partners. Top values: University of Moratuwa 3,984, Peradeniya 3,321, Sri Jayewardenepura 3,284, Colombo 3,175.
**Keep - high importance.** Backbone of institutional productivity analysis and, with `countries`, of collaboration networks. 26,211 distinct values means name variants need an alias map before grouping.

**[31] `sri_lankan_institutions`** - present 73,257 (43.00%), missing 97,108 (57.00%), 3,445 distinct, 20.1% multi-valued. OpenAlex 100% exclusively.
The domestic subset of `institutions`, equal to its parent in 56.4% of rows.
**Keep - high importance.** Far cleaner than `institutions` (3,445 vs 26,211 distinct) and pre-filtered to Sri Lanka, making it the better field for national reporting. Note that `Department of Archaeology` (3,690) is a government department, not a university - confirm this matches intended scope.

**[32] `countries`** - present 73,257 (43.00%), missing 97,108 (57.00%), 6,260 distinct, 43.1% multi-valued. OpenAlex 100% exclusively.
ISO country codes. `LK` alone covers 41,648 rows (56.9% of populated); the rest are collaborations - `AU; LK` 2,684, `LK; US` 2,570, `GB; LK` 2,514.
**Keep - high importance.** Compact, clean, and the single best field for international-collaboration analysis. Usable as-is.

### Venue and publisher fields (33-38)

**[33] `publisher`** - present 143,621 (84.30%), missing 26,744 (15.70%), 6,246 distinct. All four sources.
The best-covered venue field and the only one populated by every source.
**Keep + harmonize (priority).** `Sri Lanka Journals Online (JOL)` (12,931) and `Sri Lanka Journals Online` (10,666) are one publisher split in two, covering 16.4% of the corpus. Any publisher ranking is wrong until mapped.

**[34] `publisher_location`** - present 3,632 (2.13%), missing 166,733 (97.87%), 68 distinct. Crossref 9%, OpenAlex 4.9%.
**Drop.** Beyond sparsity, 81% is `Singapore` (1,608) plus `Cham` (1,340), which are Springer imprint registration cities. It measures Springer's corporate structure, not publishing geography.

**[35] `journal`** - present 88,403 (51.89%), missing 81,962 (48.11%), 14,509 distinct. SLJOL 100%, OpenAlex 97.4%, Crossref 93.6%, repositories 0.1%.
**Keep + harmonize, with a caveat.** The top two values are not journals: `Zenodo (CERN)` 2,262 and `SSRN Electronic Journal` 2,257, a repository and a preprint server, 4,519 rows combined. Filter on `source_type == "journal"` before treating this as a journal field.

**[36] `container_title`** and **[37] `source_name`** - both present 88,403 (51.89%), missing 81,962 (48.11%), 14,509 distinct.
Byte-identical to `journal` in all 88,403 rows, same distinct count, same top values.
**Drop both.** Entirely lossless - three columns storing one fact.

**[38] `source_type`** - present 160,684 (94.32%), missing 9,681 (5.68%), 5 distinct. Repositories 100%, SLJOL 100%, OpenAlex 86.9%, Crossref 6.4%.
**Keep, and prefer it over `type`.** The cleanest categorical field in the dataset - five tidy values at 94% coverage needing zero harmonization, against `type`'s 97 spellings of the same handful of concepts. Use it as the primary grouping variable.

### Bibliographic fields (39-46)

**[39] `issn`** and **[40] `issn_l`** - both present 52,166 (30.62%), missing 118,199 (69.38%). `issn` 11,647 distinct and 49.7% multi-valued; `issn_l` 11,384 distinct and 0.1% multi-valued. OpenAlex 71.2%, Crossref 50%.
Not duplicates despite identical coverage. `issn` is the full list (`2513-230X; 2513-2814`); `issn_l` is the canonical linking ISSN (`2513-230X`), a substring of `issn` in 100% of rows.
**Keep both.** `issn_l` is the venue join key and cannot be derived, because nothing in `issn` marks which entry is canonical.

**[41] `volume`** - present 48,175 (28.28%), missing 122,190 (71.72%), 1,224 distinct. **Keep.**
**[42] `issue`** - present 38,148 (22.39%), missing 132,217 (77.61%), 558 distinct. **Keep.**
Both required for citation strings, but see the completeness section below - among rows that have a journal, volume reaches only 53.7% and issue 42.9%.

**[43] `page`** - present 50,706 (29.76%), missing 119,659 (70.24%), 23,740 distinct.
**Drop.** Reconstructs from `first_page` + `last_page` in 99.9% of rows, and the pair is more complete.

**[44] `first_page`** - present 55,472 (32.56%), missing 114,893 (67.44%), 11,869 distinct.
**[45] `last_page`** - present 55,431 (32.54%), missing 114,934 (67.46%), 11,816 distinct.
**Keep both.** More complete than `page` and structured, so page-range arithmetic works without parsing.

**[46] `article_number`** - present 10,150 (5.96%), missing 160,215 (94.04%), 7,626 distinct. Crossref 9%, OpenAlex 13.9%.
**Keep, flagged unreliable.** Mixed quality: genuine identifiers such as `bbb.70178` sit alongside top values of `1`, `2`, `3`, `6` with counts under 30, which look like sequence numbers. Needed for e-only journals that do not use pages, but validate before relying on it.

### Language, rights and licence fields (47-50)

**[47] `language`** - present 131,389 (77.12%), missing 38,976 (22.88%), 55 distinct. OpenAlex 92.4%, repositories 79.3%, Crossref 64.1%, SLJOL 0.7%.
**Keep + harmonize.** `en` (114,079) and `en_US` (11,029) are the same language under two codes, a split affecting 8.4% of all rows; `si_lk` (1,138) and `si` (56) have the same problem. Normalizing to ISO 639-1 collapses 55 distinct values to roughly 20.

**[48] `rights`** - present 503 (0.30%), missing 169,862 (99.70%), 1 distinct.
Every populated row holds the identical boilerplate string.
**Drop.** A single distinct value carries no information by definition, and `license` / `license_url` handle rights properly.

**[49] `license`** - present 34,871 (20.47%), missing 135,494 (79.53%), 9 distinct. OpenAlex 47.6%, Crossref 1.3%.
A clean controlled vocabulary: `cc-by` 25,488 (73.1%), `cc-by-nc-nd` 3,574, `cc-by-nc` 2,374, `cc-by-sa` 1,045, plus five more.
**Keep - this is the licence field to group on.** No cleanup required.

**[50] `license_url`** - present 40,275 (23.64%), missing 130,090 (76.36%), 388 distinct, 43.2% multi-valued. Crossref 84.6%, OpenAlex 54.9%.
Complementary to `license`, not redundant: 14,555 rows have `license` only, 19,959 have `license_url` only, 20,316 have both.
**Keep, but normalize before grouping.** CC-BY 4.0 appears under four spellings - trailing slash and `http` versus `https` - totalling 10,280 rows across the top four entries.

## Drop Rules

### 1. `container_title` and `source_name` duplicate `journal`

All three columns are byte-identical in every one of the 88,403 rows where they are populated, and each has the same 14,509 distinct values.

```text
journal == container_title    88,403 / 88,403 = 100.0%
journal == source_name        88,403 / 88,403 = 100.0%
container_title == source_name 88,403 / 88,403 = 100.0%
```

Final rule:

```text
keep journal
drop container_title
drop source_name
```

This is lossless. `journal` is the clearest name for the surviving column.

### 2. `page` is derivable from `first_page` and `last_page`

`page` reconstructs exactly from the pair in 99.9% of rows where all three are present:

```text
page == first_page + "-" + last_page   36,942 / 50,577 = 73.0%
page == first_page (single-page item)  13,573 / 50,577 = 26.8%
combined                               50,515 / 50,577 = 99.9%
```

The pair is also **more complete** than `page`:

```text
first_page present, page absent : 4,895 rows
page present, first_page absent :   129 rows
```

Final rule:

```text
backfill first_page/last_page from page for the 129 affected rows
then drop page
```

Dropping `page` without the backfill loses page data for 129 rows (0.08%), which is acceptable if a backfill step is not worth building.

### 3. `rights` holds one constant string

All 503 populated rows contain the identical value:

> "This content is protected by copyright. They may be viewed, downloaded, or printed..."

One distinct value across 0.30% of rows carries no information for any analysis, and `license` / `license_url` cover licensing properly.

```text
drop rights
```

### 4. `editors` and `publisher_location` are too sparse

`editors` covers 0.70% of rows. `publisher_location` covers 2.13% and is dominated by Springer imprint cities rather than meaningful geography:

```text
Singapore  1,608  44.3%
Cham       1,340  36.9%
```

Neither supports a publication-level analysis. Recover from Crossref later if a book/chapter or publishing-geography study is ever needed.

## Keep Rules

### 5. `issn` and `issn_l` are complementary, not duplicates

They match in only 50.4% of rows, but `issn_l` is a substring of `issn` in **100%** of the 52,166 rows where both are present. `issn` is a multi-valued list (49.7% of cells hold several ISSNs); `issn_l` is the single canonical linking ISSN.

Keep both: `issn_l` is the correct grouping key for a venue, and it cannot be derived from `issn` because the list does not identify which entry is canonical.

### 6. `license` and `license_url` are complementary

```text
both populated     20,316
license only       14,555
license_url only   19,959
```

Neither is redundant. `license` is a clean 9-value vocabulary (73.1% `cc-by`); `license_url` carries the specific instrument. Keep both.

### 7. `sri_lankan_*` columns are meaningful subsets

```text
sri_lankan_authors      == authors       19.8%   (fully Sri Lankan author lists)
sri_lankan_institutions == institutions  56.4%   (fully Sri Lankan institution lists)
```

These are not duplicates - the equality rate *is* the signal. It identifies wholly domestic output versus internationally co-authored work, which is directly useful for collaboration analysis. Keep both pairs.

### 8. `source_type` needs no work

Only 5 distinct values across 94.32% coverage, already consistent:

```text
repository      92,203  57.4%
journal         64,686  40.3%
book series      2,047   1.3%
conference         932   0.6%
ebook platform     816   0.5%
```

This is the cleanest categorical field in the block and is a better grouping variable than `type`, which is fragmented across 97 spellings.

## Harmonization Required Before Analysis

These columns are worth keeping but will fragment any `group by` until normalized.

### `language` - 55 distinct, should be ~20

```text
en      114,079  86.8%
en_US    11,029   8.4%     -> en
other     4,280   3.3%
si_lk     1,138   0.9%     -> si
si           56   0.0%
```

`en` and `en_US` are the same language split across two codes, affecting 8.4% of rows. Normalize to ISO 639-1 (strip region suffixes, lowercase).

### `publisher` - 6,246 distinct, heavy variant problem

```text
Sri Lanka Journals Online (JOL)  12,931   9.00%
Sri Lanka Journals Online        10,666   7.43%
```

One publisher split across two spellings covers 16.4% of the corpus. Use the template at `configurations/user_dataset/journal_alias_template.csv` to build a mapping.

### `journal` - 14,509 distinct

Same class of problem at venue level. Harmonize after `publisher`, since publisher grouping narrows the candidate set for fuzzy venue matching.

## Bibliographic Completeness

Among the 88,403 rows that have a journal:

| Field | Rows | Coverage of journal rows |
|---|---:|---:|
| `first_page` | 55,245 | 62.5% |
| `issn` | 52,166 | 59.0% |
| `page` | 50,706 | 57.4% |
| `volume` | 47,491 | 53.7% |
| `issue` | 37,905 | 42.9% |
| `article_number` | 10,150 | 11.5% |

Roughly 40% of journal articles lack volume/page data. This is a hard ceiling on any citation-string reconstruction or reference-matching work and should be stated as a limitation rather than treated as a defect to fix.

## Resulting Schema Width

These decisions are **implemented**. `scripts/build_final_common_dataset.py` now produces a
60-column dataset. Full accounting of the 16 columns removed between the merged schema and
the final dataset:

| Change | Count | Columns |
|---|---:|---|
| Merged common schema | 76 | - |
| Dropped by doc 07 (block 51-76) | -10 | `is_referenced_by_count`, `referenced_works_count`, `references_json`, `event_name`, `event_acronym`, `event_location`, `event_start_date`, `event_end_date`, `event_sponsor`, `raw_source_json` |
| Dropped by this document (block 26-50) | -6 | `container_title`, `source_name`, `page`, `rights`, `editors`, `publisher_location` |
| Renamed away | -2 | `cited_by_count`, `funder_id` |
| Renamed in | +2 | `citation_count`, `funder_identifier` |
| **Final dataset** | **60** | `common_publications_final.csv` |

The two renames are net-neutral, which is why 18 column names disappear but only 16 columns
are lost. `references_json` is not deleted - it moves to `publication_references.csv`.

Measured effect on the real dataset:

| File | Rows | Columns | Size |
|---|---:|---:|---:|
| `common_publications_deduplicated.csv` | 170,365 | 76 | 841 MB |
| `common_publications_final.csv` | 170,365 | **60** | **320 MB** |
| `publication_references.csv` | 1,808,219 | 8 | 997 MB |

Row count is unchanged - no records are lost, only columns.

Columns 1-25 are now formally reviewed in
[09_columns_1_25_final_dataset_decisions.md](09_columns_1_25_final_dataset_decisions.md),
and the additional first-block drops are implemented in `scripts/build_final_common_dataset.py`.
The current clean main dataset target is **56** columns: 52 surviving original-schema
columns plus 4 generated count comparison columns.

## Implementation

The six drops are in the `DROP_FROM_MAIN` list in
[scripts/build_final_common_dataset.py](../scripts/build_final_common_dataset.py), grouped
under a comment naming this document so each entry traces to its decision:

```python
DROP_FROM_MAIN = [
    # ... block 51-76 entries from doc 07 ...
    # Columns 26-50, per docs/08_columns_26_50_final_dataset_decisions.md.
    "container_title",
    "source_name",
    "page",
    "rights",
    "editors",
    "publisher_location",
]
```

`test_clean_final_dataset_applies_columns_26_50_decisions` in
[tests/test_build_final_common_dataset.py](../tests/test_build_final_common_dataset.py)
asserts these six are absent **and** that `journal`, `first_page`, `last_page`, and
`publisher` survive, so a future edit cannot drop the wrong side of a duplicate pair.

### Known gap: the 129 `page` rows

`page` was dropped without the backfill described in rule 2 above. 129 rows (0.08%) had
`page` populated while `first_page` was empty; those rows now carry no page data. Add a
backfill step ahead of the drop if that matters.

## Final Verdict

Block 26-50 is in better shape than block 51-76. It carries two exact duplicate venue columns, one derivable page field, one constant-value field, and two fields too sparse to use - six drops in total, three of them entirely lossless. The remaining 19 columns are worth keeping, but `language`, `publisher`, and `journal` all need alias harmonization before they can be grouped on, and roughly 40% of journal rows lack complete volume/page metadata.
