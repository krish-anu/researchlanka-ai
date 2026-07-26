# Data Collection: Sri Lankan University Repositories

This document describes the repository data-collection subsystem: the
target registry, the harvesting scripts, the common metadata schema, and
the current per-institution status. It covers repository identification,
endpoint validation, large-scale collection, schema mapping, cross-source
enrichment, and recovery routes for repositories that cannot be harvested
at all.

For the wider platform architecture see
[SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md](SYSTEM_AND_DATA_PIPELINE_ARCHITECTURE.md);
for the canonical analysis schema see [metadata.md](metadata.md).

Last updated: 2026-07-25.

## Overview

Publications are collected from Sri Lankan university/institute
repositories (mostly DSpace, plus OJS for SLJOL) through whichever
access route each site actually supports:

1. **OAI-PMH** (`/oai/request` or `/server/oai/request`) - the standard
   bulk-metadata protocol. Preferred when it works.
2. **DSpace 7/8 REST API** (`/server/api/discover/search/objects`) -
   used where the OAI index is broken/empty but the site runs modern
   DSpace. Returns richer, qualified Dublin Core.
3. **HTML meta-tag crawl** (browse pages + `<meta name="DC.*">` tags) -
   last resort for legacy DSpace with a dead OAI index, no REST, and no
   sitemap. Only used where robots.txt does not restrict crawling.

A fourth, **cross-source** route sits alongside these:

4. **OpenAlex by institution** (`authorships.institutions.lineage:<id>`) -
   the DOI-bearing journal output an institution never deposited in its
   own repository. This is a *complement*, not another way of reading the
   repository: for cmb/pdn/uwu the two populations overlap by only ~5%
   (see the overlap table below), so it roughly doubles what we hold for
   an institution and adds citation counts, open-access status and topic
   labels that no repository route provides.

All raw data lands in `data/raw/<institution_id>/`, gets mapped into a
single common schema in `data/processed/repositories/<id>.jsonl`
(repository routes) and `data/processed/openalex/<id>.jsonl` (OpenAlex),
and is also exported as one combined CSV for easy review in Excel.

## Directory Layout

```
data/
  config/
    repositories.json          # the target registry (hand-curated, see below)
    institutions_reference.json # expected institution coverage (regression guard)
  raw/
    <id>/oai_dc.jsonl          # raw OAI-PMH harvest (flat Dublin Core)
    <id>/rest_items.jsonl      # raw DSpace REST harvest (qualified DC)
    <id>/html_meta.jsonl       # raw HTML meta-tag crawl
    <id>/openalex_works.jsonl  # raw OpenAlex works for that institution
    <id>/crossref_affiliation.jsonl  # recovery route for blocked repositories
    <id>/pubmed_works.jsonl          # recovery route for blocked repositories
  processed/
    repositories/<id>.jsonl    # common-schema records, one file per institution
    openalex/<id>.jsonl        # common-schema OpenAlex records, kept separate
    recovery/<id>.jsonl        # blocked repositories, via Crossref + PubMed
    repositories_combined.csv  # everything in one spreadsheet
  reports/
    repository_validation_*.json       # endpoint validation runs
    harvest_summary_*.json             # bulk harvest outcomes
    source_coverage_*.json             # data-quality / coverage reports
    repository_openalex_overlap_*.json # repository vs OpenAlex duplication
    institution_validation_*.json      # registry institution integrity
    registry_drift_*.json              # registry claims vs latest evidence
```

Raw and processed data files are gitignored; only the registry and
reports structure are versioned.

## The Registry: `data/config/repositories.json`

One entry per institution/platform (~35 entries covering the full
inventory). Key fields:

| Field | Meaning |
|---|---|
| `id` | Short stable identifier (`uom`, `cmb`, `nsf`, ...) used everywhere |
| `oai_endpoint` | Verified or inferred OAI-PMH base URL |
| `rest_api_endpoint` | DSpace 7/8 REST base (`/server/api`) where present |
| `browse_url` | Browse UI base, only where it differs from the server root (Jaffna) |
| `status` | `confirmed_live`, `endpoint_inferred`, `unreachable`, `blocked_for_automated_requests`, `no_repository_found`, `no_own_repository`, `skip`, `pilot_do_not_harvest` |
| `recovery_routes` | Third-party routes run for a blocked repository (kln); the status stays `blocked_for_automated_requests` so the OAI scripts keep skipping it |
| `phase` | `phase_1` (high-value new targets), `phase_2` (previously known), `not_applicable`, `deferred` |
| `harvest_route` | `rest` or `html` where OAI is not the working route; absent = OAI |
| `openalex_institution_id` | OpenAlex institution id (`I...`), enabling the cross-source route |
| `endpoint_verified_live` | Whether a real `?verb=Identify` succeeded on the recorded URL |
| `ssl_verify_failed` | Host is live but has a broken TLS certificate (SLIIT) |
| `hosted_by` | For `no_own_repository` entries, the registry id whose repository holds this institution's output (gwuas -> kln) |
| `notes` | Dated findings: what was tried, what failed, exact errors, workarounds |

The top-level `notes` array records the cross-cutting findings (http-only
hosts, the empty-OAI-index problem and its REST resolution, still-blocked
targets). **Read the notes before re-investigating any "broken"
institution - most dead ends are already documented with dates.**

## Code Map

Scripts in `scripts/` are thin CLI wrappers; the reusable logic lives in
`src/collectors/`.

| Module | Responsibility |
|---|---|
| `repository_registry.py` | Loads and filters `repositories.json`; owns the "is this target harvestable" rule |
| `oai_pmh_collector.py` | OAI-PMH `ListRecords` with resumption-token pagination |
| `dspace_rest_collector.py` | DSpace 7/8 discover endpoint, including the `owningCollection` and `bundles/bitstreams` embeds |
| `html_meta_collector.py` | Browse-page enumeration plus Dublin Core `<meta>` extraction |
| `sitemap_collector.py` | Sitemap URL discovery (diagnostic only) |
| `openalex_collector.py` | OpenAlex works API, cursor pagination |
| `crossref_collector.py` | Crossref works API, by DOI prefix or affiliation |
| `pubmed_collector.py` | NCBI E-utilities esearch + efetch, XML parsing |
| `schema_mapping.py` | One `map_*_record` function per source into the common schema |

Every collector that pages over a remote API uses a retrying session
(`create_session()`): these hosts drop connections mid-harvest routinely.
Long harvests write to a `.partial` file and swap in only on success, so a
failed retry cannot destroy a good previous harvest.

## Scripts (in workflow order)

All scripts run from the project root with no extra dependencies beyond
`requirements.txt` (only `requests` is used for collection).

### 1. `scripts/validate_repositories.py` - check endpoints before harvesting

```bash
python scripts/validate_repositories.py                  # all harvestable targets
python scripts/validate_repositories.py --phase phase_1
python scripts/validate_repositories.py --ids kln,sjp    # force-check specific ids
```

For each target: OAI `Identify` + `ListMetadataFormats`, plus a
`ListIdentifiers` probe (`has_records`) because **a live endpoint can
still have an empty OAI index** - that distinction is the single most
important lesson from Week 3. Also checks the REST API, robots.txt
permissions, and sitemap presence. Retries alternate DSpace URL patterns
(`/server/oai/request`, `/oai/request`, `/xmlui/...`, `/jspui/...`),
plain-`http` and `www.` variants, and retries once without TLS
verification (flagged, never silent) to tell bad-cert hosts from dead
hosts. Writes `data/reports/repository_validation_<timestamp>.json`.

### 2. `scripts/harvest_oai.py` - harvest one repository via OAI-PMH

```bash
python scripts/harvest_oai.py --list             # show harvestable ids
python scripts/harvest_oai.py --id uom
python scripts/harvest_oai.py --id nsf --max-records 20   # test run
```

Streams `ListRecords` with resumption-token pagination into
`data/raw/<id>/oai_dc.jsonl`. Keeps partial results if the server dies
mid-harvest. Honours the registry's `ssl_verify_failed` flag per host.

### 3. `scripts/harvest_all.py` - bulk OAI harvest of every live target

```bash
python scripts/harvest_all.py --max-records-per-target 0   # 0 = no cap
```

Runs the OAI harvest for every harvestable registry target, continuing
past per-institution failures, and writes a summary to
`data/reports/harvest_summary_<timestamp>.json`.

### 4. `scripts/harvest_large_repository.py` - date-sliced OAI workaround

```bash
python scripts/harvest_large_repository.py --id ruh --start-year 1990
```

Several DSpace hosts (cmb, ruh, seu, uwu) crash with HTTP 500 partway
through plain pagination (`No converter for [class
java.util.LinkedHashMap]` - a server-side Spring bug). This script
slices the harvest by date range and recursively halves any range that
still crashes. **Institution-specific results - check the registry notes
first**: it rescued ruh (96%) and cmb (98%), made seu *worse* (use plain
`harvest_oai.py` there), and cannot help uwu (every date-filtered query
crashes). cmb and uwu are now better served by the REST route anyway.

### 5. `scripts/harvest_dspace_rest.py` - DSpace 7/8 REST route

```bash
python scripts/harvest_dspace_rest.py --id nsf
```

Pages through the public discover endpoint
(`/server/api/discover/search/objects?dsoType=item`; note
`/server/api/core/items` returns 401 on these hosts) into
`data/raw/<id>/rest_items.jsonl`. This is the working route for **pdn,
nsf, busl** (empty OAI index) and **cmb, uwu** (OAI pagination bugs) -
all five harvested to 100% this way.

The discover endpoint also supports `embed`, which the plain metadata
response does not include:

- `owningCollection` (**on by default**) - the department/faculty that
  owns the item, e.g. "Department of Accounting". Dublin Core carries no
  faculty field at all, so this is the only structural signal for
  faculty-level analysis. Costs ~5s per 100-item page.
- `bundles/bitstreams` (`--embed-bitstreams`) - the file listing, giving
  the ORIGINAL PDF URL and DSpace's own extracted-text bitstream (full
  text, not just the abstract). **Expensive**: 40-65s per 100-item page,
  i.e. hours for a full repository. Opt in deliberately.

Use `--no-embeds` to fall back to the original metadata-only behaviour.

### 6. `scripts/harvest_html_meta.py` - HTML meta-tag crawl (last resort)

```bash
python scripts/harvest_html_meta.py --id jfn_research
```

For legacy DSpace with dead OAI, no REST, and no sitemap (the two Jaffna
repositories). Enumerates items via the public browse-by-title listing
and reads the Dublin Core `<meta>` tags DSpace embeds in every item page
- structured metadata, not screen-scraping. Only used where robots.txt
poses no restriction (both Jaffna hosts return 404 for robots.txt, i.e.
no restrictions declared). Deliberately slow (0.5s delay); expect hours
for a full run.

### 7. `scripts/discover_sitemap.py` - sitemap-based URL discovery

```bash
python scripts/discover_sitemap.py --id uom --max-urls 100
```

Discovers item URLs from `sitemap_index.xml`/`sitemap.xml`. Currently a
diagnostic tool (no metadata extraction); kept for future use.

### 8. `scripts/collect_openalex_institution.py` - cross-source route

```bash
python scripts/collect_openalex_institution.py --id cmb
python scripts/collect_openalex_institution.py --all        # every registry entry with an OpenAlex id
```

Harvests every OpenAlex work affiliated with the institution into
`data/raw/<id>/openalex_works.jsonl`, using the registry's
`openalex_institution_id`. The filter is `lineage` rather than `id` so
faculty/hospital sub-institutions recorded under the university are
included. Cursor-paginated at 200/page, no year bounds by default
(`--from-year`/`--to-year` narrow it).

Abstracts arrive as OpenAlex's `abstract_inverted_index` and are
reconstructed to plain text by the mapper.

### 9. `scripts/collect_sljol.py` - SLJOL via Crossref

```bash
python scripts/collect_sljol.py --email you@example.com
```

sljol.info itself blocks scripted access, so Crossref's public API is the
sanctioned route to the same bibliographic metadata, harvested by the
platform's DOI prefix `10.4038` into `data/raw/sljol/crossref_works.jsonl`.
Note that these records mostly lack abstracts and keywords, and carry no
author affiliation strings at all - so SLJOL data cannot be re-attributed
to individual universities. If affiliations or abstracts are needed,
request official SLJOL access from NSF.

### 10. Recovery routes for blocked repositories

Two third-party routes reach an institution's output when its own
repository cannot be harvested at all. Both are affiliation-scoped and
neither involves touching the blocked host.

```bash
python scripts/collect_crossref_affiliation.py --id kln
python scripts/collect_pubmed_affiliation.py --id kln
```

- **Crossref** (`crossref_affiliation.jsonl`) - `query.affiliation` is a
  *fuzzy* full-text match, so every work is re-checked locally against
  `crossref_affiliation_match` and dropped unless an affiliation string
  really contains it. Without that check, "University of Kelaniya"
  matches on "University" alone and returns millions of unrelated works;
  with the query narrowed to `Kelaniya`, precision was 1,794/1,794.
- **PubMed** (`pubmed_works.jsonl`) - `[Affiliation]` is an exact field
  search needing no local re-check, and the records carry abstracts and
  MeSH terms. Medical/life-science output only, so it complements rather
  than replaces the Crossref route.

Registry fields: `crossref_affiliation_query`,
`crossref_affiliation_match`, `pubmed_affiliation_query`,
`pubmed_affiliation_match`, and `recovery_routes` listing what has been
run. The blocked repository keeps its `blocked_for_automated_requests`
status so the OAI scripts still skip it.

Unlike the repository routes, these two are **merged** rather than made
to compete: they cover overlapping populations, so `map_to_common_schema.py`
deduplicates them on DOI, keeps the Crossref record and fills its empty
fields from the PubMed twin. Output lands in
`data/processed/recovery/<id>.jsonl`.

### 11. `scripts/map_to_common_schema.py` - unify into the common schema

```bash
python scripts/map_to_common_schema.py --all
python scripts/map_to_common_schema.py --id uom
```

Maps each institution's raw records into the common publication schema
(below). When an institution has data from multiple *repository* routes,
**the route that captured the most records wins**; routes are never
merged, so the same item can't appear twice. Prints which route was used
per institution.

OpenAlex is deliberately kept out of that contest - it is a second
population for the same institution, not another reading of the
repository - so it is mapped separately into
`data/processed/openalex/<id>.jsonl` and can never displace repository
records.

### 12. `scripts/convert_repositories_jsonl_to_csv.py` - Excel-friendly export

```bash
python scripts/convert_repositories_jsonl_to_csv.py
```

Flattens every processed file into
`data/processed/repositories_combined.csv` (list fields joined with
`; `). Close the CSV in Excel before re-running - Windows locks open
files.

### 13. `scripts/validate_harvested_data.py` - coverage & quality report

```bash
python scripts/validate_harvested_data.py
```

Per institution: raw vs mapped record counts, duplicate source IDs,
missing titles, implausible years, malformed OAI identifiers, and
mismatches between registry claims and actual data. Uses the latest
harvest summary to explain zero-record institutions with the real error.
Writes `data/reports/source_coverage_<timestamp>.json`.

### 14. `scripts/validate_institutions.py` - registry institution integrity

```bash
python scripts/validate_institutions.py
python scripts/validate_institutions.py --quiet --no-report
```

Checks the registry's *description of each institution*, which the other
two validators do not touch: duplicate ids and names, valid
status/phase/group values, the fields a given status implies (a
`confirmed_live` entry must say how to reach it), `hosted_by` pointing at
a real entry, recovery routes carrying the query fields they need,
coverage against `data/config/institutions_reference.json`, orphaned
processed data with no registry entry, and entries whose declared status
is contradicted by records on disk.

Exits 1 on error-severity findings so it can gate CI. Missing `notes` is
deliberately a *warning*, not an error - undocumented is incomplete, not
provably wrong, and gating CI on prose nobody can reconstruct after the
fact would only invite filler.

Read `institutions_reference.json`'s `provenance` field before quoting
its coverage check: the list was derived from the registry, so it is a
regression guard against entries disappearing, not independent proof that
the registry is complete. Reconcile it against the UGC's published list
and set `verified_against_ugc` before making a completeness claim.

### 15. `scripts/detect_registry_drift.py` - registry vs reality

```bash
python scripts/validate_repositories.py        # gather fresh evidence first
python scripts/detect_registry_drift.py
python scripts/detect_registry_drift.py --max-age-days 14
```

The registry is hand-curated and 15 university servers change underneath
it without notice. This reconciles each recorded claim against the latest
validation report and the raw files on disk:

| Drift | Meaning |
|---|---|
| `endpoint_died` | status says live, the endpoint no longer answers |
| `endpoint_recovered` | status says unreachable/blocked, the endpoint now answers |
| `stale_verification` | `endpoint_verified_live` is true but validation failed |
| `endpoint_moved` | validation had to fall back to a different URL |
| `index_emptied` | the OAI index now returns nothing while OAI records are stored - a re-harvest would lose them |
| `route_mismatch` / `route_undeclared` | `harvest_route` disagrees with the largest raw file on disk |

It makes no network requests, so it is cheap to run in CI; it reports how
old its evidence is and warns past `--max-age-days`. Exits 1 when drift
is found.

**Two false-positive traps this deliberately avoids**, both learned from
real registry entries:

- Never compare against the server's self-reported `<baseURL>`. DSpace
  instances routinely advertise a canonical hostname they are not served
  from - busl answers on `dl-busl.nsf.gov.lk` while advertising
  `repo.busl.ac.lk`. Only the URL that actually worked is evidence.
- Normalise explicit default ports and trailing slashes before comparing,
  or `http://host/oai/request` and `http://host:80/oai/request` read as
  an endpoint change (vpa).

### 16. `scripts/compare_repository_openalex.py` - cross-source overlap

```bash
python scripts/compare_repository_openalex.py
python scripts/compare_repository_openalex.py --ids cmb,pdn --report
```

Per institution: how many OpenAlex works duplicate a repository record
(DOI first, then normalised title) and how many are genuinely new, so the
combined figure is never double-counted. Repository records rarely carry
a DOI, so title matching does most of the work - treat the duplicate
counts as a lower bound.

## Common Publication Schema

Every processed record has these fields (null/empty where unavailable):

| Field | Notes |
|---|---|
| `source` | Always `institutional_repository` for this subsystem |
| `source_institution_id` | Registry `id` |
| `source_record_id` | OAI identifier, REST UUID, or handle path |
| `source_datestamp` | Repository-side last-modified/accession date |
| `title`, `abstract` | First value where the source is multi-valued |
| `authors`, `contributors`, `keywords` | Lists |
| `publication_date`, `publication_year` | Issued date; year extracted best-effort |
| `publication_type` | As declared by the repository (not yet standardized) |
| `publisher`, `language`, `rights` | As declared |
| `doi` | Extracted by regex from identifier fields (rare in repository data) |
| `url` | Item landing page (handle URL) |
| `raw_identifiers` | Everything the source put in its identifier fields |
| `deleted` | True for OAI tombstones, withdrawn DSpace items and retracted works; these are filtered out during mapping, never written to the processed files |
| `source_set_specs` | OAI setSpec values where the route provides them; empty for every other route |

Qualified Dublin Core (the REST route) and OpenAlex carry more than the
flat OAI feed, so these fields are populated where the source has them
and left null elsewhere:

| Field | Notes |
|---|---|
| `collection` | Owning department/faculty (REST `embed=owningCollection`) |
| `journal` | `dc.relation.ispartof`, or the OpenAlex source name |
| `citation` | Full citation string - often the only venue signal (pdn, uwu) |
| `series`, `volume`, `issue` | Series and `oaire.citation.*` bibliographic detail |
| `isbn`, `issn` | As declared |
| `funding` | Sponsorship statements (repository) / funder names (OpenAlex) |
| `alternative_title` | `dc.title.alternative` |
| `pdf_url`, `fulltext_url`, `file_count` | Only with `--embed-bitstreams` |
| `cited_by_count`, `is_open_access`, `oa_status`, `topics`, `affiliated_institutions` | OpenAlex only |

Field standardization (types, names, dates) is Week 4's cleaning work -
this schema is the *collection* contract, deliberately close to the
source.

## Current Status (2026-07-25)

**160,613 records** collected: 126,455 from repository routes, 30,221
net-new OpenAlex works for cmb/pdn/uwu, and 3,937 recovered for Kelaniya
and Sabaragamuwa, whose repositories cannot be harvested at all.

| id | Institution | Records | Route | Coverage |
|---|---|---|---|---|
| sljol | SLJOL (176 journals, via Crossref prefix 10.4038) | 26,200 | Crossref | 100%+ |
| uom | Moratuwa | 16,565 | OAI | ~100% |
| nsf | NSF national aggregator | 15,792 | REST | 100% |
| ruh | Ruhuna | 14,743 | OAI date-sliced | ~96% |
| jfn_research | Jaffna (UJRR) | 11,049 | HTML meta | ~100% |
| uwu | Uva Wellassa | 8,897 | REST | 100% |
| pdn | Peradeniya (new instance) | 7,692 | REST | 100% of new server |
| cmb | Colombo | 8,452 | REST | 100% |
| seu | South Eastern | 5,902 | OAI | ~88% (server bug) |
| sliit | SLIIT | 4,057 | OAI | ~100% |
| jfn_medicine | Jaffna (Medicine) | 3,758 | HTML meta | ~100% |
| busl | Buddhasravaka Bhiksu | 2,873 | REST | 100% |
| sltc | SLTC | 475 | OAI | ~100% |

SLJOL is also exported standalone as `data/processed/sljol.csv`. Note
Crossref-sourced SLJOL records mostly lack abstracts/keywords; if those
are needed for topic modelling, request official SLJOL access from NSF.

### Cross-source enrichment (2026-07-25)

OpenAlex harvested for the three institutions that carry an
`openalex_institution_id`. Duplicates are counted against the repository
records by DOI then normalised title
(`scripts/compare_repository_openalex.py`):

| id | Repository | OpenAlex | Duplicate | Net new | Combined unique |
|---|---|---|---|---|---|
| cmb | 8,452 | 14,776 | 1,540 | 13,236 | 21,688 |
| pdn | 7,692 | 15,257 | 73 | 15,184 | 22,876 |
| uwu | 8,897 | 1,818 | 17 | 1,801 | 10,698 |
| **total** | **25,041** | **31,851** | **1,630** | **30,221** | **55,262** |

Two things drive the near-zero overlap: repository holdings are mostly
theses, conference papers and locally published work that was never
indexed, and repository records almost never carry a DOI (cmb 13%, pdn
and uwu 0%), so only cmb has enough DOIs for DOI-level matching. Treat
the duplicate column as a lower bound.

The OpenAlex side is also richer per record: ~97% carry a DOI, ~64-80%
an abstract, and all of them carry citation counts, open-access status
and topic labels.

### Recovery results (2026-07-25)

Two institutions whose repositories cannot be harvested at all are now
partly covered through the Crossref + PubMed affiliation routes:

| id | Crossref | PubMed | Merged unique | Years | DOI | Abstract |
|---|---|---|---|---|---|---|
| kln (Kelaniya) | 1,794 | 1,939 | **3,207** | 1977-2026 | 98% | 74.5% |
| sab (Sabaragamuwa) | 587 | 219 | **730** | 1998-2026 | 100% | 65% |

What both still miss is exactly what a repository holds and a publisher
index does not: theses and internal proceedings that never got a DOI.

#### Affiliation matching is institution-specific

Neither route can be pointed at an institution name and left alone:

- **Crossref's `query.affiliation` is fuzzy.** "University of Kelaniya"
  returns 21.8 million works by matching "University" alone. Narrowed to
  `Kelaniya` plus a local affiliation re-check, precision was 1,794/1,794.
- **Some institution names are also place names.** "Sabaragamuwa" is a
  province, so the bare name matches a Provincial Director of Health
  Services office and two 1895 colonial medical-officer papers. `sab`
  therefore carries a `pubmed_affiliation_regex`
  (`sabaragamuwa\s+univ|univ\w*\s+of\s+sabaragamuwa`) which drops
  exactly those four.
- **That regex is deliberately not applied to Crossref**, and not to
  `kln` at all. Crossref affiliation strings are publisher-entered and
  mangled ("University of Sri Lanka,Faculty of Computing Sabaragamuwa,..."),
  so the strict pattern would drop 5 genuine SUSL records to remove 2 bad
  ones. On the Kelaniya side it would discard "University of Kalaniya" and
  "Univeristy of Kelaniya" - real records whose institution name is
  misspelled at source.

Known residue, left in on purpose: 2 provincial-office records in the sab
Crossref set, and 3 non-university matches in kln (a plantation company, a
bare "Kelaniya, Sri Lanka", and one Uva Wellassa record with a Kelaniya
postal address). Tightening further costs more real records than it saves.

### Kelaniya (2026-07-25)

The repository is still 403 - re-checked with a plain identified request,
and per the exclusions below no header spoofing, proxying or headless
browsing was attempted. The Crossref set breaks down as 1,115 journal
articles, 493 proceedings papers and 186 preprints; 526 records are shared
with PubMed and were merged rather than duplicated.

Two dead ends worth not repeating: `journals.kln.ac.lk` is an
unconfigured Joomla demo site (lorem-ipsum articles), not a journal
platform; `lib.kln.ac.lk` and `www.kln.ac.lk` respond but expose no
metadata endpoint.

### Ruhuna went unreachable (2026-07-25)

`ir.lib.ruh.ac.lk` failed 0/4 HTTPS `Identify` attempts today (connect
timeout on 443/80/8080), having harvested fine on 2026-07-19/20.
`www.ruh.ac.lk` still serves 200, so the outage is specific to the
repository host. The 14,743 records already collected are intact on disk;
the registry status is deliberately left `confirmed_live` rather than
`unreachable` because the host may be intermittent - a bare TCP connect
to 443 did succeed once. Re-check before concluding it is dead.

### Sabaragamuwa (2026-07-25)

`repo.lib.sab.ac.lk` resolves to 192.248.87.19 but TCP-times-out on 80,
443 **and** 8080, while `www.sab.ac.lk` (192.248.87.24, same /24) answers
on 443 from the same machine. That disproves the standing "possibly our
own network blocking port 8080" theory - an outbound block on non-standard
ports would not explain 80 and 443 failing too. The host is down or
firewalled server-side. The main site still links to
`http://repo.lib.sab.ac.lk:8080/xmlui/`, so the URL remains canonical.

### Peradeniya's legacy instance

`dlib.pdn.ac.lk` was re-checked on 2026-07-25 and is still completely
unreachable (connect timeout on http/https/www/:8080). The historic
collection it held remains out of reach; OpenAlex now covers Peradeniya's
journal output back to the same era, but not its theses.

### Blocked - needs outreach (no technical workaround)

| Target | Problem | Ask |
|---|---|---|
| kln (Kelaniya) | WAF blocks all scripted requests (403); not in CORE; AGRIS covers agriculture only. **Partly recovered 2026-07-25** via Crossref + PubMed affiliation routes (3,207 records) - what stays locked is repository-only content: theses and internal proceedings never published with a DOI | API access / allow-listing |
| pgim | OAI returns 403 specifically; site otherwise fine | Enable public OAI |
| ou, vpa, rjt, esn, vau | OAI live but index empty; legacy DSpace, no REST/sitemap. **ou**: CORE aggregates OUSL (provider 13528) - a free CORE API key could recover a copy | Run `dspace oai import` to rebuild index |
| kdu | Cloudflare 522 - DSpace backend down | Fix origin server |
| sjp | Connection dropped on every request | Investigate server |
| sab | Host unreachable on 80/443/8080 - server-side, not our network (retested 2026-07-25). **Partly recovered**: 730 records via Crossref + PubMed | Fix origin server |
| wyb | Host unreachable on 80/443 | Investigate server |
| ucsc | Live JSPUI site, but no OAI path exists | Enable OAI |
| pdn (legacy) | Old `dlib.pdn.ac.lk` offline; may hold historic collection | Ask about migration status |

### Deliberate exclusions

- **SLJOL / Kelaniya WAF**: we do not attempt to circumvent bot
  protection (spoofed headers, proxies, headless browsers). Access to the
  blocked host goes through a formal request or not at all. Collecting
  the same institution's output from third-party indexes that publish it
  openly (Crossref, PubMed - see the recovery routes above) is a
  different thing and is fine; it never touches the blocked host.
- **dspace.ac.lk (LEARN)**: near-empty pilot; revisit quarterly.
- **Private/SLIATE institutes** except SLIIT: no research repositories.

## Refreshing Everything

```bash
# 1. (optional) re-check endpoint health
python scripts/validate_repositories.py

# 2. harvest per route (see registry harvest_route field)
python scripts/harvest_all.py --max-records-per-target 0        # OAI targets
python scripts/harvest_dspace_rest.py --id pdn                  # + nsf, busl, cmb, uwu
python scripts/harvest_html_meta.py --id jfn_research           # + jfn_medicine (slow)

# 2b. cross-source enrichment
python scripts/collect_openalex_institution.py --all

# 2c. recovery routes for blocked repositories
python scripts/collect_crossref_affiliation.py --id kln
python scripts/collect_pubmed_affiliation.py --id kln

# 3. map, validate, export
python scripts/map_to_common_schema.py --all
python scripts/validate_harvested_data.py
python scripts/validate_institutions.py
python scripts/detect_registry_drift.py
python scripts/compare_repository_openalex.py --report
python scripts/convert_repositories_jsonl_to_csv.py
python scripts/convert_repositories_jsonl_to_csv.py \
    --input data/processed/openalex \
    --output data/processed/openalex_combined.csv
```

Do not run two harvesters for the same institution concurrently - they
write to the same raw file.
