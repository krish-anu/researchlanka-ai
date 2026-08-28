# Backend Code Audit

Full-backend correctness sweep. Frontend was explicitly out of scope.

**Date:** 2026-08-24
**Scope:** `backend/` — `src/`, `research_analytics/`, `scripts/`, `tests/`, packaging
**Method:** full test run, byte-compile of every module, import of every module and
script, AST scan for redefinitions / mutable defaults / bare excepts, dependency
diff, markdown link check, and end-to-end runs of the repaired scripts against the
real 170k-row dataset.

| | Before | After |
|---|---|---|
| Test suite | **could not collect** (1 import error) | 476 passed, 3 xfailed |
| Tests failing | 13 | 0 |
| Modules that fail to import | 6 | 0 |
| Scripts that fail to import | 2 | 0 |

---

## Part 1 — Defects found and fixed

### 1. Model artifact saving was broken on Windows *(12 failing tests)*

`src/modeling/artifacts.py` — `dump_joblib_artifact` reopened the just-written
pickle `"rb"` and called `os.fsync` on it. Windows rejects `fsync` on a
read-only descriptor with `OSError: [Errno 9] Bad file descriptor`, so **every**
model save failed: classifier training, model comparison, and embedding
generation.

Fixed by opening `"r+b"` — writable, non-truncating, and identical on POSIX.
`fsync_directory` was hardened at the same time to swallow `OSError` from the
`fsync` call itself, not just from `os.open`, since Windows supports neither.

> This one root cause accounted for 12 of the 13 test failures.

### 2. Crossref affiliation collection could never run

`src/collectors/crossref_collector.py` defined `iter_works` **twice**. The
second definition silently shadowed the real, working implementation and
delegated to `self.iter_affiliation_works` — a method that did not exist. It
also dropped the `filters` argument.

Every affiliation-based caller was therefore broken two ways:

- `research_analytics/adapters/crossref.py:39` — passes `filters`
- `src/pipeline/collect_crossref.py:213` — passes `filters`

Fixed by renaming the real implementation to `iter_affiliation_works` (the name
the alias always expected) and making `iter_works` a genuine alias that forwards
all four arguments.

### 3. Six `src/utils` modules were un-importable

Every one imported the shared helper as a top-level `utils` package:

```python
from utils.column_resolve import clean_str      # ModuleNotFoundError
```

The package is `src.utils`, and `pytest.ini` pins `pythonpath = .` to the
backend root, so the bare name never resolved. Affected:
`author_utils`, `date_utils`, `journal_utils`, `publisher_utils`,
`referece_utils`, `title_utils`. All corrected to `src.utils.column_resolve`.

### 4. The test suite could not be collected at all

`tests/test_extractors.py` imported `src.extractors.journal` and three siblings.
**`src/extractors/` contains no `.py` files and has never been tracked in git** —
only a stale `__pycache__` remains from a local refactor. Because a collection
error aborts the whole run, this single file blocked all 447 other tests.

The extractors moved to `src/utils/*_utils.py` and changed contract along the
way: they now read the **flat common schema** (`journal`, `publication_date`,
`authors`) rather than raw Crossref/OpenAlex payloads, so the old assertions
could not be salvaged as written.

The file was rewritten against the modules that actually exist, giving these
six previously-untested modules real coverage. Three `xfail`-marked tests encode
the open question in [Part 2.2](#22-column-priority-lists-contradict-their-own-docstrings).

### 5. Two extraction scripts imported a module that was never committed

`scripts/extraction/extract_authors.py` and `extract_titles.py` both did:

```python
from utils.io_utils import load_dataset, save_dataset
```

`io_utils` **does not exist anywhere in the repository**, and neither
`load_dataset` nor `save_dataset` is defined anywhere. Both scripts died at
import.

Fixed by adding `src/utils/io_utils.py` — a deliberately thin CSV/Parquet
loader/saver, covered by `tests/test_io_utils.py`. CSV is read with `dtype=str`
and `keep_default_na=False` so DOIs, ORCIDs and the literal country code `"NA"`
survive a round trip. Both scripts now run end-to-end on the real dataset.

Their `sys.path` bootstrap was also wrong — it pushed `backend/scripts` rather
than the backend root, a leftover from when the scripts sat one directory
higher. The docstring usage lines had the same stale path.

### 6. `extract_publisher` silently dropped `publisher_location`

`src/utils/publisher_utils.py` promised the field in three places — the module
docstring ("no collapsing is needed here"), the function's own `Returns:` block,
and the column list `extract_publisher_batch` uses for an empty frame — but the
return dict omitted it. `extract_publisher_batch` therefore produced **two
columns for an empty DataFrame and one for a populated one**. Field restored.

### 7. `extract_publication_date_batch` declared phantom columns

The same class of bug: the empty-frame column list in `src/utils/date_utils.py`
included `published_date` and `created_date`, which the extractor never returns.
Trimmed to match, with a comment noting the two must stay in sync.

### 8. `rapidfuzz` was missing from `pyproject.toml`

Present in `requirements.txt`, absent from `[project.dependencies]`, so
`pip install -e .` produced an installation where
`research_analytics.duplicate_analysis` raised `ModuleNotFoundError` on import.
Declared. A full diff of the two dependency lists shows no other gaps and no
version disagreements.

### 9. Broken documentation link

`backend/README.md` linked to `docs/GITHUB_MANAGEMENT.md`, which does not exist.
It was the only broken relative link in the backend's 32 markdown files.

---

## Part 2 — Needs a decision (not fixed)

These are judgment calls that belong to the team, not to a cleanup pass.

### 2.1 The committed final dataset is stale — one pipeline stage cannot run

**This is the highest-impact open item.**

`src/pipeline/build_columns_filtered_dataset.py` raises `ValueError` when its
input lacks any `FINAL_MAIN_COLUMNS` entry. Run against the committed
`data/processed/common/common_publications_final.csv`, it fails:

```
Input dataset is missing finalized columns: author_ids,
author_disambiguation_level, citation_count_difference_oa_minus_crossref,
citation_count_divergence_flag, reference_count_difference_oa_minus_crossref,
reference_count_divergence_flag
```

The CSV was generated before the author-disambiguation and count-divergence work
landed:

| | Count |
|---|---|
| `FINAL_MAIN_COLUMNS` declares | 58 |
| The committed CSV has | 60 |
| Declared but **absent** from the CSV | 6 |
| Present in the CSV but no longer declared | 8 |

Absent: `author_ids`, `author_disambiguation_level`,
`citation_count_difference_oa_minus_crossref`, `citation_count_divergence_flag`,
`reference_count_difference_oa_minus_crossref`,
`reference_count_divergence_flag`.

Undeclared extras: `landing_page_url`, `subtitle`, `original_title`,
`created_date`, `published_date`, `subtype`, `publication_type`, `author_names`.

Note that the API's `BASE_COLUMNS` in `src/api/repositories/sql.py` *does*
expect the six disambiguation/divergence columns, so the database load path and
the committed CSV disagree about the schema.

**Decision needed:** re-run the pipeline from `build_final_common_dataset`
onward (with author disambiguation enabled) to regenerate the CSV, or amend
`FINAL_MAIN_COLUMNS` if those columns are no longer intended. This is a data
operation with real cost, so it was deliberately left alone.

### 2.2 Column-priority lists contradict their own docstrings

Every `*_PRIORITY` list in `src/utils/` holds exactly one column, while the
module docstring above it describes a multi-column fallback chain:

| Module | Constant | Docstring describes |
|---|---|---|
| `journal_utils` | `["journal"]` | `journal`, `container_title`, `source_name` |
| `date_utils` | `["publication_date"]` | + `published_date`, `created_date`, `publication_year` |
| `referece_utils` | `["reference_count"]` | + `referenced_works_count` |
| `author_utils` | `["authors"]` | **`author_names` first**, then `authors` |

`author_utils` is the sharpest: its docstring states "`author_names` IS the
intended shared/normalized field, so it takes priority; `authors` is used only
when `author_names` is empty" — the constant does the exact opposite.

Two readings, and the team should pick one:

- **Intended.** Upstream normalization already collapses these into the
  canonical column, so a one-element list is correct and the docstrings are
  stale leftovers from the raw-payload era.
- **A regression.** The lists were truncated during the `src/extractors` →
  `src/utils` move and the fallbacks should be restored.

Three `xfail(strict=False)` tests in `tests/test_extractors.py` encode the
documented behaviour. If the fallbacks are restored they turn green on their
own; if the narrow behaviour is confirmed, delete them and fix the docstrings.

### 2.3 The `src/utils` extractors are dead code

Nothing in `src/pipeline/`, `src/api/`, or `research_analytics/` imports any of
`author_utils`, `date_utils`, `journal_utils`, `publisher_utils`,
`referece_utils`, or `title_utils`. Their only consumers are the two repaired
scripts and the test file. Worth confirming whether they are the intended
future home for this logic (currently duplicated inside the pipeline stages) or
an abandoned branch that should be deleted.

### 2.4 Filename typo: `referece_utils.py`

Should be `reference_utils.py`. Not renamed unilaterally — a tracked-filename
change invites conflicts with in-flight branches, and nothing but the new test
imports it. Cheap to do whenever the branch queue is clear.

### 2.5 String formatting that mimics SQL placeholders

In `src/api/repositories/sql.py`, `build_where` builds three clauses with
Python `%` formatting that reads exactly like a psycopg parameter:

```python
clauses.append("is_oa IS %s" % ("TRUE" if filters["is_oa"] else "FALSE"))
clauses.append("doi IS %s NULL" % ("NOT" if filters["has_doi"] else ""))
```

**Not a live vulnerability** — the substituted values are hardcoded literals,
and every genuine user value in that function is correctly parameterized. But
the two forms are visually identical, and the surrounding lines *are* real
placeholders, so a maintainer could easily introduce injection by dropping a
filter value into this shape. Suggest rewriting as plain conditionals with
literal SQL strings.

The rest of the SQL layer checks out: identifiers come from fixed dicts and go
through `quote_identifier`, `SORT_SQL` is a dict lookup with a safe fallback,
and no user input reaches `select_columns`.

### 2.6 Two different stage vocabularies

`research_analytics.cli` and `run_pipeline.py` are both documented entry points
but expose different stage names:

- `cli`: `source-validate`, `preview`, `validate`, `import`, `clean`,
  `deduplicate`, `analyze`, `load_database`, `run-all`, `generate_embeddings`
- `run_pipeline.py`: `collect`, `transform`, `validate`, `clean`,
  `resolve_entities`, `deduplicate`, `analyze`, `load_database`, `export`, `all`

Only `validate`, `clean`, `deduplicate`, `analyze`, and `load_database` are
common. Newcomers reliably trip on this. Either align them or state plainly in
the README that `run_pipeline.py` is the finer-grained stage runner.

### 2.7 Minor

- `research_analytics/duplicate_analysis.py:491` — `evaluate_thresholds(df, thresholds=[90, 92, 95, 97, 99])`
  uses a mutable default. The list is only iterated, never mutated, so it is a
  style smell rather than a live bug. A tuple would settle it.
- **Docstring coverage is 29%** for public functions (349/1217); classes are at
  61%. See [BACKEND_ARCHITECTURE_MAP.md](BACKEND_ARCHITECTURE_MAP.md) for the
  orientation this partly compensates for, and the per-file table below for
  where new docstrings would pay off most.

Lowest-coverage files with five or more public functions:

| Public fns documented | File |
|---|---|
| 0/39 | `src/api/services/publications.py` |
| 0/33 | `src/pipeline/build_analysis_ready_dataset.py` |
| 0/28 | `scripts/processing/fetch_missing_author_emails.py` |
| 0/27 | `src/pipeline/build_final_common_dataset.py` |
| 0/17 | `src/quality/manual_review_ui.py` |
| 0/13 | `research_analytics/pipeline.py` |
| 0/11 | `src/api/transport/http_server.py` |
| 0/11 | `scripts/analysis/columns/analyze_first_25_columns.py` |
| 0/10 | `src/pipeline/build_multivalue_normalized_dataset.py` |

---

## Part 3 — Confirmed clean

Checks that found nothing, recorded so they are not repeated:

- **Syntax** — every module under `src/`, `research_analytics/`, and `scripts/`
  byte-compiles.
- **Imports** — all 191 modules import cleanly; all 49 scripts import cleanly.
  (`research_analytics.duplicate_analysis` needs `rapidfuzz` installed, now
  declared in both dependency files.)
- **Redefinitions** — no remaining shadowed functions, methods, or classes after
  the `iter_works` fix.
- **Bare `except:`** — none anywhere in the backend.
- **Mutable default arguments** — one, noted in 2.7.
- **SQL injection** — the API query builder parameterizes all user input; see
  2.5 for the readability caveat.
- **Dependency drift** — `requirements.txt` and `pyproject.toml` agree on every
  package and version after the `rapidfuzz` fix.
- **Markdown links** — one broken link, fixed; the other 31 files are clean.
- **`TODO`/`FIXME`/`HACK` markers** — none in backend Python or SQL.
