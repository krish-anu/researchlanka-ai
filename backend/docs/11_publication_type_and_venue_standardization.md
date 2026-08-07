# Publication Type and Venue Standardization

Status: Complete
Covers: Week 4 tasks — standardize publication types, standardize journal names.

## Purpose

The same output is described differently by every source. OpenAlex says
`journal-article`, Crossref says `article`, and university repositories say
`Article-Full-text`. The corpus contained **97 distinct type values** for what is
really about two dozen genres.

Venue names were in much better shape than expected, but the `journal` field
frequently held a platform name rather than a journal.

## Results

Measured on 170,365 records:

| Metric | Before | After |
|---|---|---|
| Distinct publication types | 97 | **27** |
| Records identified as research outputs | not distinguished | **150,704 (88.5%)** |
| Venue names rewritten | — | 235 across 20 spellings |
| Records whose venue is a platform, not a journal | not distinguished | **9,459** |

Type distribution: journal_article 101,688 · conference_paper 20,620 ·
unknown 15,537 · thesis 12,000 · preprint 4,901 · exam_paper 3,898 ·
book_chapter 3,204 · abstract 2,098.

Venue types: unknown 81,962 (no venue recorded — mostly theses and repository
items) · journal 64,949 · conference 9,864 · preprint_server 4,341 ·
data_repository 4,093 · other_venue 3,831 · book_series 995 · aggregator 260 ·
institutional_repository 70.

## Standardizing without losing information

Repository type values encode three separate facts in one string.
`Thesis-Abstract` says the genre is a thesis, the record holds only an abstract,
and the degree level is unstated. Collapsing that to `thesis` would silently
destroy the second fact — which matters, because whether a record has full text
determines whether it can be used for text-based machine learning.

Each fact therefore gets its own column:

| Column | Values |
|---|---|
| `publication_type_standardized` | 27-term controlled vocabulary |
| `record_form` | `full_text`, `abstract`, `unknown` |
| `thesis_degree_level` | `masters`, `mphil`, `phd`, `unknown` |
| `is_research_output` | boolean |

So `Thesis-Full-text` and `Thesis-Abstract` both become `thesis`, distinguished
by `record_form`; `PhD Thesis` and `Masters Thesis` both become `thesis`,
distinguished by `thesis_degree_level`.

### Research outputs

`is_research_output` is False for `exam_paper`, `journal_issue`, `paratext`,
`media`, `non_research` and `unknown`. This removes 19,661 records from research
counts — 3,898 exam papers, plus convocation booklets, tables of contents,
front matter, animations and videos — without deleting them from the dataset.

Report research statistics over `is_research_output == True`, or the counts will
include exam papers.

### The `unknown` bucket

15,537 records (9.1%). It comes from four raw values that carry no recoverable
meaning — `Other` (10,202), `A` (2,069), `other` (527), `P` (12) — plus 2,727
records with no type at all. `A` and `P` are repository codes whose meaning is
not documented; if the source institutions can explain them, those 2,081 records
become recoverable.

## Venue standardization

### Journals were already clean

The raw count of 14,509 distinct journals suggested a large normalization
problem. It is not one. Only **16 groups** differed by case alone and only
**7 ISSNs** carried more than one spelling. The merge stage had already applied
its field-source policy, which favours the OpenAlex and Crossref canonical
names. Sri Lankan research genuinely spans roughly 14,500 venues.

Total rewrites: 235 records, 20 distinct spellings.

### Canonical names come from corpus evidence

Rather than a hand-written mapping, the stage runs two passes. The first counts
every spelling and every ISSN-to-name pairing; the second rewrites each record
to the dominant spelling. Two passes are required because the dominant spelling
is only knowable after the whole corpus has been read.

Resolution order:

1. **ISSN, when present.** An ISSN is an identifier, so records sharing one are
   the same venue however the name was written. This is what maps a record
   labelled `PubMed` back to `Epidemiology`.
2. **Dominant spelling of the case-folded group**, e.g.
   `DESALINATION AND WATER TREATMENT` → `Desalination and Water Treatment`.
3. **Publisher qualifier removed**, but only when a shorter spelling of the same
   venue is already attested — `arXiv (Cornell University)` → `arXiv`.

Ties are broken towards natural title case. Without that rule an even split
between `Journal of the Postgraduate Institute of Medicine` and
`Journal Of The Postgraduate Institute of Medicine` resolves alphabetically, and
uppercase sorts first, so the worse spelling would win.

A parenthetical is only removed when it names a publisher or host organisation,
or repeats the venue name. A series qualifier is part of the venue's identity
and is kept: `Ceylon Journal of Science (Biological Sciences)` is not the same
venue as `Ceylon Journal of Science`.

### The venue field often holds a platform

9,459 records name a preprint server, data repository or aggregator in the
`journal` field — Zenodo (2,262), SSRN (2,257), Archaeology Data Service (1,265),
Research Square (1,259), figshare, bioRxiv, medRxiv, PubMed. Counting these as
journals would badly distort venue statistics, so `venue_type` labels them
instead of discarding them.

`proceedings` is deliberately **not** treated as a conference marker, because it
appears in journal titles such as *Proceedings of the National Academy of
Sciences*. Genuine conference venues in this corpus all carry `conference`,
`symposium`, `workshop` or `congress` as well.

## Running

```bash
make type-journal-normalize
```

Reads the institution-normalized dataset, so run `make institution-normalize`
first.

Outputs, in `data/processed/common/`:

- `common_publications_final_type_journal_normalized.csv` — all input columns
  plus the six derived columns
- `..._type_journal_normalized_summary.csv` — the metrics above
- `publication_type_mapping.csv` — every raw type value and what it became
- `journal_name_mapping.csv` — every venue rewrite

Both mapping files exist for review: they make each decision auditable rather
than buried in code.

## Known limitations

- The type vocabulary is keyword-driven. A genuinely new type value from a future
  source falls through to `unknown` rather than failing loudly.
- `A` and `P` (2,081 records) are unresolved repository codes.
- Venue classification is keyword-based. A conference whose name contains none of
  the marker words is classified `other_venue` (3,831 records).
- ISSN canonicalization only helps the 11,384 venues that carry an ISSN. Venues
  without one rely on spelling alone.
