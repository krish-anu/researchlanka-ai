# Institution Code Walkthrough

Developer guide for the institution, affiliation, country and collaboration code.

For **what the rules are and what results they produced**, read
[10_institution_and_affiliation_standardization.md](10_institution_and_affiliation_standardization.md).
This document is about **how the code is put together** — where to make a change, and what will
break if you make it in the wrong place.

---

## 1. Where the code lives

Three files, one test file.

| File | Lines | Role |
|---|---|---|
| `research_analytics/institutions.py` | 554 | All logic. Registry, matching, parsing, classification |
| `src/pipeline/build_institution_registry.py` | 464 | Generates `configurations/sri_lanka/institutions.csv` |
| `src/pipeline/build_institution_normalized_dataset.py` | 427 | Applies the registry to the merged dataset |
| `tests/test_institution_normalization.py` | 42 tests | Grouped by concern |

**Why two layers.** The logic sits in `research_analytics/` so the config-driven framework pipeline
can call it — `ResearchPipeline.resolve_entities()` uses `enrich_national_context()` directly. The
`src/pipeline/` stage applies the same functions to the 170,365-row CSV. **There is no second
implementation**; if you change a rule in `institutions.py`, both paths change.

Data in and out:

```
configurations/sri_lanka/institutions.csv   <- registry (generated, hand-reviewed)
data/config/repositories.json               <- repository codes -> institution names
data/processed/common/common_publications_final.csv
        |
        v  build_institution_normalized_dataset.py
common_publications_final_institution_normalized.csv
..._institution_normalized_summary.csv
common_publications_final_unresolved_institutions.csv
```

---

## 2. One record's journey

A repository row arrives with no institution, no country, and no affiliation — only
`source_institution_id = "uom"`. Here is every function it touches.

| Step | Function | Result |
|---|---|---|
| 1 | `normalize_row()` | starts with empty `institutions` |
| 2 | `split_multi_value("")` | `[]` — no metadata names |
| 3 | `parse_affiliation("")` | `([], [])` — nothing to parse |
| 4 | `registry.resolve_from_source_id("uom")` | `[Institution(LK003)]` |
| 5 | | `institution_source = "source_institution_id"` |
| 6 | `registry.resolve_names(["University of Moratuwa"])` | resolved `[LK003]`, unresolved `[]` |
| 7 | `standardize_countries("")` | `([], [])` — no country given |
| 8 | | LK inferred, because a national institution resolved |
| 9 | `classify_collaboration()` | `domestic_single_institution` |
| 10 | `collaboration_scope()` | `local` |

Inside step 4, `resolve_from_source_id` checks `NON_INSTITUTION_SOURCE_IDS` first. Had the code been
`"sljol"`, it would return `[]` and the record would end as `unknown` — SLJOL is a journal platform
hosting many universities, so the collection source implies nothing about the institution.

Inside step 6, `resolve_names` calls `resolve_name` per value, which calls `_lookup_candidates` to
build the keys to try, each produced by `normalize_lookup_key`.

---

## 3. `institutions.py` — the logic

### The registry

`Institution` (line 152) is a plain dataclass: id, preferred name, country code, alias set, ROR id,
parent id, type, and the set of repository source codes.

`NationalInstitutionRegistry` (line 163) builds **two indexes** in `__init__`:

- `alias_index: dict[str, str]` — normalized name key → institution id
- `source_id_index: dict[str, str]` — repository code (`uom`, `cmb`) → institution id

Both are built once at construction. `_index_alias` uses `setdefault`, so **the first alias to claim
a key wins** — later duplicates do not silently overwrite an earlier mapping.

Two constructors: `from_csv()` (line 183) takes explicit column names and is what the pipeline stage
uses; `from_config()` (line 228) reads them from `FrameworkConfig` and is what the framework uses.

### Matching

This is the part to understand before changing anything.

```
resolve_names(value)          -> splits, then per value:
  resolve_name(name)          -> tries each candidate key in order
    _lookup_candidates(name)  -> [full key, progressively shorter comma-prefixes]
      normalize_lookup_key()  -> the actual key construction
```

`normalize_lookup_key` (line 381) applies, in order:

1. Unicode NFKD normalization; replacement characters and curly quotes normalized
2. `_strip_subunit_prefixes` — drops leading `Department of`, `Faculty of`, `Division`, `Unit`,
   `Laboratory`, `Section`, `Chair`, `Clinic`, `Ward`, `Library`, **only while another
   comma-separated segment remains**
3. `TRAILING_COUNTRY_RE` — drops a trailing `, Sri Lanka`
4. `ABBREVIATION_PATTERNS` — `Univ.`→`University`, `Center`→`Centre`, `&`→`and`, etc.
5. lowercase, all non-alphanumeric runs collapsed to single spaces

`_lookup_candidates` (line 406) returns the full key first, then keys built from progressively
shorter comma-prefixes. This is what makes `University of Peradeniya, Peradeniya 20400` resolve. The
loop stops before the first segment, so a name is never reduced past its own head.

Matching is **exact-key only** — there is no fuzzy matching anywhere. That is deliberate: every
resolution can be explained by pointing at the alias that produced it.

### Source-code resolution

`resolve_from_source_id` (line 270) maps `uom` → LK003. It consults `source_id_index` first, then
falls back to `alias_index` (registry rows list bare codes such as `cmb` as aliases too). Codes in
`NON_INSTITUTION_SOURCE_IDS` (line 27) never resolve.

### Splitting

`split_multi_value` (line 518) splits on **semicolons only**. See invariant 2.

### Affiliations and countries

`parse_affiliation` (line 438) returns `(institution_names, country_hints)`. Per semicolon-separated
part it strips sub-unit prefixes, then uses `_country_matches` (line 473) to detect country names.
A detected country is removed from the name **only when a comma precedes it** — see invariant 3.

`standardize_country` (line 484) returns an ISO 3166-1 alpha-2 code or `None`.
`standardize_countries` (line 503) returns `(codes, unrecognised)` — unrecognised values are
reported, never silently dropped.

### Collaboration

`enrich_national_context` (line 294) is the framework entry point: resolve, then classify, then set
scope. It has a `registry is None` branch that falls back to country-only classification.

`classify_collaboration` (line 337) returns one of five types; `collaboration_scope` (line 355)
reduces those to three:

| `collaboration_type` | `collaboration_scope` |
|---|---|
| `domestic_single_institution` | `local` |
| `domestic_multi_institution` | `local` |
| `international_collaboration` | `international` |
| `unresolved_affiliation` | `unknown` |
| `not_national` | `unknown` |

### Legacy wrappers — do not "clean up"

`_as_list` (line 536) and `_normalize_name` (line 540) are thin wrappers over `split_multi_value`
and `normalize_lookup_key`. They are kept because other modules and tests import them. Deleting them
looks like tidying and breaks callers.

---

## 4. `build_institution_registry.py` — generating the registry

Run order inside `build_institution_registry()` (line 420):

```
read_seed_counts()       -> Counter of names from the sri_lankan_institutions column
read_existing_registry() -> (existing entries, key -> id index)
load_source_id_map()     -> repository code -> institution name
build_registry_rows()    -> the rows
write_registry()         -> configurations/sri_lanka/institutions.csv
find_possible_duplicates() -> printed for review, never auto-merged
```

**Seeding.** `read_seed_counts` (line 179) reads the `sri_lankan_institutions` column, which is
OpenAlex's own country-filtered list — every value in it is already confirmed Sri Lankan, so no
separate country check is needed. It raises `ValueError` if the column is missing.

**Two non-obvious behaviours in `build_registry_rows` (line 243):**

1. **Curated aliases run as a pre-pass and act as merge hints.** Before seeding, every key in
   `CURATED_ALIASES` that already maps to an existing institution registers *all* its sibling keys
   to that same id. This is why the dataset spelling `National Science Foundation of Sri Lanka`
   attaches to the existing `National Science Foundation` (LK006) instead of becoming LK045.
   Without this pre-pass the two do not share a lookup key and you get a duplicate institution.

2. **Existing ids are preserved.** Existing entries are inserted into `records` first, and seeded
   names attach to them via `key_to_id`. Only genuinely new institutions call
   `next_institution_id` (line 236).

**Supporting functions.** `infer_institution_type` (line 228) walks `TYPE_KEYWORDS` in order, first
match wins — order matters, `hospital` is checked before `university`. `find_possible_duplicates`
(line 370) reports institution pairs whose normalized names nest inside one another, which is the
shape a missed merge takes. It reports only; distinct institutions can legitimately nest.

---

## 5. `build_institution_normalized_dataset.py` — the stage

`normalize_row` (line 116) is the whole stage for one record. It recovers institutions in **three
ordered passes, most confident first**:

| Pass | Source | `institution_source` | Real corpus |
|---|---|---|---|
| 1 | `institutions` metadata | `metadata` | 73,257 |
| 2 | `source_institution_id` | `source_institution_id` | 80,233 |
| 3 | `author_affiliations` | `author_affiliations` | 7 |
| — | nothing available | `none` | 16,868 |

Pass 3 also runs additively when passes 1 or 2 succeeded, adding co-affiliations the earlier passes
missed.

After resolution the row gets country codes from three sources, in order: the `countries` field via
`standardize_countries`, then `parse_affiliation`'s hints, then `LK` inferred when a national
institution resolved.

Six columns are added, listed in `ADDED_COLUMNS` (line 81):

```
national_institution_ids   national_institutions   unresolved_institutions
institution_source         collaboration_type      collaboration_scope
```

**`NormalizationStats`** (line 93) is a mutable accumulator threaded through every `normalize_row`
call. Adding a metric means adding a counter here, incrementing it in `normalize_row`, and emitting
it in `write_summary` (line 259).

**Streaming.** `iter_normalized_chunks` (line 229) reads with `pandas.read_csv(chunksize=25_000)` and
the caller writes each chunk as it arrives, so memory stays flat on the 336 MB input. Any change
that accumulates all rows in a list defeats this.

Three outputs: the dataset, `write_summary`, and `write_unresolved` (line 322) — the last is the
feedback loop for improving the registry.

---

## 6. Recipes

### Add an institution or an alias

Edit `CURATED_ALIASES` in `src/pipeline/build_institution_registry.py` (line 107), keyed by the
institution's preferred name:

```python
"University of Kelaniya": ("UOK", "Kelaniya University", "Univ of Kelaniya"),
```

Then:

```bash
python -m src.pipeline.build_institution_registry
git diff configurations/sri_lanka/institutions.csv    # review before committing
python -m src.pipeline.build_institution_normalized_dataset
```

Generation is deterministic, so the diff shows only what you actually changed — anything else in it
is a real change worth understanding.

To find what is worth adding, sort `common_publications_final_unresolved_institutions.csv` by
mentions. Anything Sri Lankan above roughly 50 mentions is worth an entry.

### Map a new repository collection code

Add to `SOURCE_ID_TO_INSTITUTION` (line 67), using the institution name **as it appears in the
dataset**, not as it appears in `repositories.json`:

```python
"kln": "University of Kelaniya",
```

### Stop a code implying an institution

Add it to `NON_INSTITUTION_SOURCE_IDS` in `research_analytics/institutions.py` (line 27). Use this
for platforms and aggregators that host many institutions' output.

### Recognise another country name

Add to `COUNTRY_NAME_TO_CODE` (line 81), lowercase key:

```python
"myanmar": "MM",
```

### Accept a country code outside official ISO 3166-1

Add it to the `ISO_3166_1_ALPHA_2` frozenset with a comment explaining why, following the `XK`
(Kosovo) precedent — OpenAlex emits it and the records are real.

### Add a department prefix to strip

Extend `SUBUNIT_PREFIX_RE` (line 32). Remember it only fires when another comma-separated segment
remains, so standalone government departments stay intact.

### Add an abbreviation expansion

Extend `ABBREVIATION_PATTERNS` (line 48). This affects the lookup key on **both** sides, so existing
registry aliases re-normalize too — regenerate nothing, but do re-run the stage.

### Change institution-type inference

Edit `TYPE_KEYWORDS` (line 164). Order matters: first match wins.

---

## 7. Invariants

Break one of these and nothing raises — results just quietly go wrong. Each has a test.

| # | Invariant | Test |
|---|---|---|
| 1 | `normalize_lookup_key` must be used for **both** the alias index and the lookup | `test_alias_index_and_lookup_share_one_normalization` |
| 2 | Never comma-split institution, affiliation or country fields | `test_institution_name_containing_comma_is_not_split` |
| 3 | The country strip in `parse_affiliation` needs its comma guard | `test_parse_affiliation_drops_country_only_when_it_is_an_address_tail` |
| 4 | `_lookup_candidates` must never reduce past the first segment | `test_registry_does_not_resolve_an_unrelated_institution_by_prefix` |
| 5 | Institution ids are stable across regeneration | `test_registry_generation_preserves_existing_identifiers` |
| 6 | Records are never dropped; unresolved names are retained | `test_row_records_unresolved_institutions_without_dropping_them` |
| 7 | Report `national_resolution_rate` alongside `institution_resolution_rate` | `test_summary_reports_national_resolution_separately` |
| 8 | Registry generation must be deterministic | `test_registry_row_order_is_deterministic` |

Four of these came from defects found in practice, not from theory:

- **2** — `Eastern University, Sri Lanka` (920 mentions) was being split into two institutions, and
  `Ministry of Health, Nutrition and Indigenous Medicine` (1,077) into three.
- **3** — without the comma guard, `Rajarata University of Sri Lanka` truncated to
  `Rajarata University of`. This passed unit tests and only appeared in the full run.
- **7** — `institution_resolution_rate` is 50.2% because it counts Oxford, Melbourne and UCL, which
  a national registry can never resolve. The number that measures registry quality is
  `national_resolution_rate`, at 100.0%. Quoting the first as if it were the second understates the
  work by half.
- **8** — aliases live in a `set`, and the sort key used only `alias.lower()`. Case variants such as
  `PDN` and `pdn` therefore compared equal and fell back to set iteration order, which varies with
  the hash seed. Regenerating an unchanged registry produced a spurious four-line diff every time,
  which is exactly the noise that hides a real change during review. The sort key now ends in
  `alias`, making it total.

---

## 8. Testing and debugging

Tests are grouped by concern with `# ---` banners. Add yours to the matching group:

```
multi-value splitting      lookup keys           registry resolution
countries                  affiliation parsing   collaboration classification
row normalization          end to end            registry generation
```

The shared `registry` fixture builds a four-row in-memory registry from `REGISTRY_ROWS` covering
LK001 (University of Colombo, alias UOC, code `cmb`), LK003 (Moratuwa, code `uom`) and LK028
(Eastern University, Sri Lanka, code `esn`). Use it unless you need a different registry shape, in
which case write the CSV into `tmp_path` as the end-to-end tests do.

Every test is offline. Nothing touches the network or the database.

```bash
python -m pytest tests/test_institution_normalization.py -q
```

### When a result looks wrong

| Symptom | Look at |
|---|---|
| A name that should resolve does not | `normalize_lookup_key(name)` vs the registry alias's key — print both |
| A foreign institution resolved to a Sri Lankan one | `_lookup_candidates` — a prefix matched too aggressively |
| Institution coverage dropped after a change | `institution_source` counts in the summary — which pass stopped firing |
| Collaboration type looks wrong | the `countries` column first; `classify_collaboration` reads it, not the institution list |
| A record has an institution it should not | `resolve_from_source_id` — the code may need adding to `NON_INSTITUTION_SOURCE_IDS` |
| Coverage will not go above 90% | expected. 16,824 SLJOL records carry no institution signal in any field |

---

## Related

- [10_institution_and_affiliation_standardization.md](10_institution_and_affiliation_standardization.md) — the rules and the results
- [11_publication_type_and_venue_standardization.md](11_publication_type_and_venue_standardization.md) — the sibling stage. `research_analytics/venues.py` follows the same shape as this module and has no walkthrough of its own yet
- [PIPELINE_RUNBOOK.md](PIPELINE_RUNBOOK.md) — where these stages sit in the full pipeline
