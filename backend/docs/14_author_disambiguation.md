# Author Disambiguation

How author mentions are resolved onto stable author identities, what evidence
each merge rests on, and how ambiguous cases reach a human.

Code: [`research_analytics/authors.py`](../research_analytics/authors.py) (rules),
[`src/pipeline/build_author_disambiguated_dataset.py`](../src/pipeline/build_author_disambiguated_dataset.py)
(pipeline), [`src/quality/review_ambiguous_authors.py`](../src/quality/review_ambiguous_authors.py)
(review queue). Tests: [`tests/test_author_disambiguation.py`](../tests/test_author_disambiguation.py).

---

## 1. The problem

`authors` is a semicolon-joined name list. `author_orcids` (12.7% of records),
`author_affiliations` (39.6%) and the normalized institution fields describe the
**record**, not an author position. There is no per-author affiliation column to
join on, so identity has to be rebuilt from what co-occurs on a record.

Two properties of this corpus shape every rule below:

- Name strings collide constantly. Sri Lankan surname distributions are heavily
  concentrated, and sources emit initials (`Perera, K.`), Vancouver style
  (`Perera KMN`), full names, and transliteration variants of the same person.
- ORCID is the only field that identifies a person outright, and 87% of records
  do not have one.

## 2. Unit of resolution: the name variant

Every distinct spelling becomes one **name variant**, keyed
`surname|given.tokens` (`perera|k`, `perera|kumara.nimal`). Variants are what
merge; records are then labelled from the variant their authors parsed into.

This has two consequences worth stating plainly:

- Identical spellings of a name are one variant by construction. Two different
  people who always publish as `Perera, K.` **cannot** be separated by these
  rules — they are one identity, surfaced for review, never silently split.
- Memory is bounded by the number of distinct spellings rather than the number
  of authorships, which is what makes a full-corpus run affordable.

### Name parsing

`parse_author_name` handles the four shapes present in the corpus:

| Input | Surname | Given |
|---|---|---|
| `Perera, Kumara Nimal` | `perera` | `kumara`, `nimal` |
| `Kumara Nimal Perera` | `perera` | `kumara`, `nimal` |
| `Perera, K.M.N.` | `perera` | `k`, `m`, `n` |
| `Perera KMN` (Vancouver) | `perera` | `k`, `m`, `n` |

Honorifics (`Prof.`, `Dr.`), degree and generational suffixes (`PhD`, `MBBS`,
`Jr`) are removed; accents are folded; surname particles stay attached
(`van der Berg`, `de Silva`). An entirely upper-cased string disables the
Vancouver rule, so `ANNE SILVA` keeps `Anne` as a given name instead of reading
it as four initials.

**Blocking key** is `surname|first-initial`. Only variants sharing a blocking
key are ever compared, except for ORCID, which links across blocks so a name
change or transliteration difference still resolves.

**Compatibility** (`names_compatible`): same surname, and no position where both
sides are spelled out and disagree. An initial matches a full name starting with
that letter; a missing middle name never blocks a match.

## 3. Merge rules, strongest first

| # | Method | Rule | Confidence |
|---|---|---|---|
| 0 | `reviewed` | A reviewer ruled on the pair. Outranks everything below. | high |
| 1 | `orcid` | Same validated ORCID → same person, across surname blocks. | high |
| 2 | `affiliation` | Compatible names sharing an institution. | medium |
| 3 | `coauthor` | Compatible names sharing at least one coauthor. | medium |
| 4 | `name` | An initialled name joins the **only** spelled-out name in its block that it fits, when no affiliation contradicts it. | low |

A cluster that no rule ever merged reports `singleton`. Nothing merges on a
similarity score. Every merge names the evidence that produced it, recorded per
cluster in `merge_evidence`, so any identity can be explained and any rule
re-run.

**Rule 1 — ORCID.** Identifiers are validated against their ISO 7064 MOD 11-2
check digit before use; a malformed one is discarded rather than becoming a
false identity anchor. An ORCID is attached to an author position only when it
can be tied to one without guessing: written inline next to the name, or the
record's ORCID list has exactly one entry per author. A list of two ORCIDs
against five authors is dropped, because a wrongly attached ORCID would merge
two different people under the strongest rule in the system.

**Differing ORCIDs are a hard block.** No automatic rule may merge two variants
whose ORCID sets are non-empty and disjoint. Blocked attempts are counted in
`merges_blocked_by_orcid_conflict`.

**Rule 2 — affiliation.** Registry identifiers (`id:LK001`) are preferred.
Records the registry could not resolve still carry usable evidence, so their
institution names are reduced with the registry's own lookup key and used as
`aff:` keys — an unresolved institution shared by two spellings is the same
signal, it just cannot be named canonically.

**Rule 3 — coauthor.** The shared unit is the coauthor's blocking key.
`--min-shared-coauthors` raises the bar from one shared coauthor to N.

**Two spelled-out names that disagree are a hard block too.** `Perera, K.` is
compatible with both `Perera, Kumara` and `Perera, Kamal`, who are not
compatible with each other. Without a gate, the shared initial would drag them
into one identity by transitivity. So:

- a merge is refused whenever the two clusters hold same-surname spelled-out
  names that disagree (counted as `merges_blocked_by_name_conflict`); and
- an initialled spelling whose evidence points at two such people is left on its
  own and queued as `evidence_points_to_more_than_one_person`. Attaching it to
  whichever candidate the loop reached first would be arbitrary.

ORCID and reviewed merges are exempt: both outrank a spelling.

**Rule 4 — name.** The weakest rule, and deliberately conservative: it applies
only when the block leaves no choice. `Perera, K.` merges into `Perera, Kumara`
when that is the sole compatible spelled-out name; add a `Perera, Kalpana` and
`K.` stays separate and both pairs go to review. If the two candidates both know
their institutions and share none, that counter-evidence blocks the merge and
sends the pair to review instead. Clusters built this way are flagged
`merged_on_name_only`.

## 4. Author identifiers

`author_id` is `A` + 11 hex characters, derived from the cluster's anchor: its
lowest ORCID, or its lowest variant key when it has none. An author keeps the
same identifier between runs for as long as that anchor keeps resolving to them.
Identifiers are not order-dependent — the same corpus produces the same ids
whatever order records arrive in.

## 5. Running it

```bash
make author-disambiguate PYTHON=python
# or
python -m src.pipeline.build_author_disambiguated_dataset
```

Reads `common_publications_final_institution_normalized.csv`, so run
`institution-normalize` first — without it, rule 2 falls back to affiliation
text and resolves less.

Two passes: the first indexes name variants and their evidence, the second
writes identifiers back onto the records.

### Added columns

| Column | Meaning |
|---|---|
| `author_ids` | Resolved identities, positional against the parsed authors. |
| `author_match_methods` | Evidence behind each identity, same order. |
| `author_disambiguation_level` | Weakest method among the record's authors: `reviewed`, `orcid`, `affiliation`, `coauthor`, `name`, `singleton`, `none`. |
| `ambiguous_author_flag` | Any of the record's authors belongs to a flagged identity. |

Names are never rewritten and records are never dropped: identities are added
alongside the original `authors` string.

### Outputs

| File | Contents |
|---|---|
| `common_publications_final_author_disambiguated.csv` | The dataset with the four columns above. |
| `author_registry.csv` | One row per identity: preferred name, variants, ORCIDs, institutions, publications, year range, method, confidence, review reasons. |
| `common_publications_final_author_disambiguation_summary.csv` | What the run resolved and how, with threshold pass flags. |
| `author_review_candidates.csv` | Pairs the rules could not settle. |

## 6. Reviewing ambiguous authors

The review queue holds pairs of identities whose names could belong to one
person but which no ORCID, affiliation or coauthor connects. Pairs with
conflicting ORCIDs are **not** queued — those are settled, not ambiguous.

```bash
make author-review PYTHON=python        # what is waiting, heaviest pairs first
```

Reasons attached to a queued pair or a flagged identity:

| Reason | Meaning |
|---|---|
| `compatible_names_no_evidence` | The names fit; nothing links them. |
| `evidence_points_to_more_than_one_person` | An initialled name has evidence with two people who cannot be the same. |
| `initials_only_name` | At least one side is initials only, so its identity is weak. |
| `merged_on_name_only` | Built by rule 4 — check it before relying on it. |
| `manual_merge_overrides_orcid_conflict` | A reviewer merged across differing ORCIDs. |
| `surname_block_too_large_for_pairwise_review` | The block exceeded `--max-block-variants`; it clustered on ORCID only. |

`needs_review` is set once a pair carries `--review-mention-threshold` mentions
between its two sides (default 5). Smaller pairs stay in the file, unflagged.

### The decision loop

1. Open `author_review_candidates.csv` and fill in `decision`
   (`same_author` / `different_author`), `reviewer` and `note`.
2. `make author-decisions PYTHON=python` — promotes the filled rows into
   `configurations/sri_lanka/author_decisions.csv` and validates the result.
3. `make author-disambiguate PYTHON=python` — applies them.

Decisions are keyed on **variant keys**, not author ids: a variant key is stable
across runs, while an identifier moves when its cluster changes. A reviewed pair
leaves the queue and stays out of it, so the queue shrinks rather than being
re-answered. A cluster built from a verdict reports `reviewed` at `high`
confidence, and once every question about a spelling has been answered it stops
marking its records ambiguous.

Order of application: reviewed splits are registered before any rule runs, so a
"different people" verdict cannot be undone by a later automatic merge. Reviewed
merges run last and win — including over an ORCID conflict, which a duplicate
ORCID registration can legitimately require. Such a cluster is flagged
`manual_merge_overrides_orcid_conflict` and counted in the summary.

`--validate` reports contradictions (a pair recorded both ways) and stale keys
(a decision naming a variant that no longer exists, usually because upstream
cleaning changed the spelling).

## 7. Quality gates

Written to the summary with `_pass` flags:

| Metric | Threshold | Why |
|---|---|---|
| `mention_assignment_rate` | 100% | Every parsed mention must get an identity. |
| `orcid_linked_cluster_rate` | 5% | A floor for noticing that ORCID handling regressed, not a target. |
| `entity_fuzzy_auto_resolution_enabled` | always `False` | Fuzzy matching is review-only by design. |

## 8. Limits

- Two people sharing one exact spelling are one identity (§2).
- ORCIDs on records whose list length does not match the author count are unused.
- Rule 4 will occasionally over-merge an initialled name in a block that has one
  spelled-out candidate but a second, absent, real person. The block only
  protects against people it can see.
- Coauthor evidence treats a shared coauthor blocking key as distinctive; a
  prolific hub author with a common name can link two distinct researchers.
- The API's `disambiguation_level` still reports `name` for researcher profiles:
  the read model aggregates publications by author name string. Pointing it at
  `author_ids` is a database-schema change and is not part of this pipeline.

See also [11_metadata_quality_limitations.md](11_metadata_quality_limitations.md)
and [10_institution_and_affiliation_standardization.md](10_institution_and_affiliation_standardization.md).
