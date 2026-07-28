# Data Collection: Sri Lankan University Repositories

This document describes the repository data-collection subsystem: the
target registry, the harvesting scripts, the common metadata schema, and
the current per-institution status. It covers the work of Weeks 1-3
(repository identification, endpoint validation, large-scale collection,
and schema mapping).

Last updated: 2026-07-20.

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

All raw data lands in `data/raw/<institution_id>/`, gets mapped into a
single common schema in `data/processed/repositories/<id>.jsonl`, and is
also exported as one combined CSV for easy review in Excel.

## Directory Layout

```
data/
  config/
    repositories.json          # the target registry (hand-curated, see below)
  raw/
    <id>/oai_dc.jsonl          # raw OAI-PMH harvest (flat Dublin Core)
    <id>/rest_items.jsonl      # raw DSpace REST harvest (qualified DC)
    <id>/html_meta.jsonl       # raw HTML meta-tag crawl
  processed/
    repositories/<id>.jsonl    # common-schema records, one file per institution
    repositories_combined.csv  # everything in one spreadsheet
  reports/
    repository_validation_*.json  # endpoint validation runs
    harvest_summary_*.json        # bulk harvest outcomes
    source_coverage_*.json        # data-quality / coverage reports
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
| `phase` | `phase_1` (high-value new targets), `phase_2` (previously known), `not_applicable`, `deferred` |
| `harvest_route` | `rest` or `html` where OAI is not the working route; absent = OAI |
| `endpoint_verified_live` | Whether a real `?verb=Identify` succeeded on the recorded URL |
| `ssl_verify_failed` | Host is live but has a broken TLS certificate (SLIIT) |
| `notes` | Dated findings: what was tried, what failed, exact errors, workarounds |

The top-level `notes` array records the cross-cutting findings (http-only
hosts, the empty-OAI-index problem and its REST resolution, still-blocked
targets). **Read the notes before re-investigating any "broken"
institution - most dead ends are already documented with dates.**

## Scripts (in workflow order)

All scripts run from the project root with no extra dependencies beyond
`requirements.txt` (only `requests` is used for collection).

### 1. `scripts/quality/validate_repositories.py` - check endpoints before harvesting

```bash
python scripts/quality/validate_repositories.py                  # all harvestable targets
python scripts/quality/validate_repositories.py --phase phase_1
python scripts/quality/validate_repositories.py --ids kln,sjp    # force-check specific ids
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

### 2. `scripts/collection/harvest_oai.py` - harvest one repository via OAI-PMH

```bash
python scripts/collection/harvest_oai.py --list             # show harvestable ids
python scripts/collection/harvest_oai.py --id uom
python scripts/collection/harvest_oai.py --id nsf --max-records 20   # test run
```

Streams `ListRecords` with resumption-token pagination into
`data/raw/<id>/oai_dc.jsonl`. Keeps partial results if the server dies
mid-harvest. Honours the registry's `ssl_verify_failed` flag per host.

### 3. `scripts/collection/harvest_all.py` - bulk OAI harvest of every live target

```bash
python scripts/collection/harvest_all.py --max-records-per-target 0   # 0 = no cap
```

Runs the OAI harvest for every harvestable registry target, continuing
past per-institution failures, and writes a summary to
`data/reports/harvest_summary_<timestamp>.json`.

### 4. `scripts/collection/harvest_large_repository.py` - date-sliced OAI workaround

```bash
python scripts/collection/harvest_large_repository.py --id ruh --start-year 1990
```

Several DSpace hosts (cmb, ruh, seu, uwu) crash with HTTP 500 partway
through plain pagination (`No converter for [class
java.util.LinkedHashMap]` - a server-side Spring bug). This script
slices the harvest by date range and recursively halves any range that
still crashes. **Institution-specific results - check the registry notes
first**: it rescued ruh (96%) and cmb (98%), made seu *worse* (use plain
`harvest_oai.py` there), and cannot help uwu (every date-filtered query
crashes). cmb and uwu are now better served by the REST route anyway.

### 5. `scripts/collection/harvest_dspace_rest.py` - DSpace 7/8 REST route

```bash
python scripts/collection/harvest_dspace_rest.py --id nsf
```

Pages through the public discover endpoint
(`/server/api/discover/search/objects?dsoType=item`; note
`/server/api/core/items` returns 401 on these hosts) into
`data/raw/<id>/rest_items.jsonl`. This is the working route for **pdn,
nsf, busl** (empty OAI index) and **cmb, uwu** (OAI pagination bugs) -
all five harvested to 100% this way.

### 6. `scripts/collection/harvest_html_meta.py` - HTML meta-tag crawl (last resort)

```bash
python scripts/collection/harvest_html_meta.py --id jfn_research
```

For legacy DSpace with dead OAI, no REST, and no sitemap (the two Jaffna
repositories). Enumerates items via the public browse-by-title listing
and reads the Dublin Core `<meta>` tags DSpace embeds in every item page
- structured metadata, not screen-scraping. Only used where robots.txt
poses no restriction (both Jaffna hosts return 404 for robots.txt, i.e.
no restrictions declared). Deliberately slow (0.5s delay); expect hours
for a full run.

### 7. `scripts/collection/discover_sitemap.py` - sitemap-based URL discovery

```bash
python scripts/collection/discover_sitemap.py --id uom --max-urls 100
```

Discovers item URLs from `sitemap_index.xml`/`sitemap.xml`. Currently a
diagnostic tool (no metadata extraction); kept for future use.

### 8. `scripts/processing/map_to_common_schema.py` - unify into the common schema

```bash
python scripts/processing/map_to_common_schema.py --all
python scripts/processing/map_to_common_schema.py --id uom
```

Maps each institution's raw records into the common publication schema
(below). When an institution has data from multiple routes, **the route
that captured the most records wins**; routes are never merged, so the
same item can't appear twice. Prints which route was used per
institution.

### 9. `scripts/processing/convert_repositories_jsonl_to_csv.py` - Excel-friendly export

```bash
python scripts/processing/convert_repositories_jsonl_to_csv.py
```

Flattens every processed file into
`data/processed/repositories_combined.csv` (list fields joined with
`; `). Close the CSV in Excel before re-running - Windows locks open
files.

### 10. `scripts/quality/validate_harvested_data.py` - coverage & quality report

```bash
python scripts/quality/validate_harvested_data.py
```

Per institution: raw vs mapped record counts, duplicate source IDs,
missing titles, implausible years, malformed OAI identifiers, and
mismatches between registry claims and actual data. Uses the latest
harvest summary to explain zero-record institutions with the real error.
Writes `data/reports/source_coverage_<timestamp>.json`.

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

Field standardization (types, names, dates) is Week 4's cleaning work -
this schema is the *collection* contract, deliberately close to the
source.

## Current Status (2026-07-20)

**126,440 records** collected from 12 institutions plus SLJOL:

| id | Institution | Records | Route | Coverage |
|---|---|---|---|---|
| sljol | SLJOL (176 journals, via Crossref prefix 10.4038) | 26,200 | Crossref | 100%+ |
| uom | Moratuwa | 16,565 | OAI | ~100% |
| nsf | NSF national aggregator | 15,792 | REST | 100% |
| ruh | Ruhuna | 14,743 | OAI date-sliced | ~96% |
| jfn_research | Jaffna (UJRR) | 11,049 | HTML meta | ~100% |
| uwu | Uva Wellassa | 8,897 | REST | 100% |
| cmb | Colombo | 8,447 | REST | 100% |
| pdn | Peradeniya (new instance) | 7,682 | REST | 100% of new server |
| seu | South Eastern | 5,902 | OAI | ~88% (server bug) |
| sliit | SLIIT | 4,057 | OAI | ~100% |
| jfn_medicine | Jaffna (Medicine) | 3,758 | HTML meta | ~100% |
| busl | Buddhasravaka Bhiksu | 2,873 | REST | 100% |
| sltc | SLTC | 475 | OAI | ~100% |

SLJOL is also exported standalone as `data/processed/sljol.csv`. Note
Crossref-sourced SLJOL records mostly lack abstracts/keywords; if those
are needed for topic modelling, request official SLJOL access from NSF.

### Blocked - needs outreach (no technical workaround)

| Target | Problem | Ask |
|---|---|---|
| kln (Kelaniya) | WAF blocks all scripted requests (403); not in CORE; AGRIS covers agriculture only. Journal articles still arrive via OpenAlex; theses stay locked | API access / allow-listing |
| pgim | OAI returns 403 specifically; site otherwise fine | Enable public OAI |
| ou, vpa, rjt, esn, vau | OAI live but index empty; legacy DSpace, no REST/sitemap. **ou**: CORE aggregates OUSL (provider 13528) - a free CORE API key could recover a copy | Run `dspace oai import` to rebuild index |
| kdu | Cloudflare 522 - DSpace backend down | Fix origin server |
| sjp | Connection dropped on every request | Investigate server |
| sab | Port 8080 unreachable (possibly our network) | Retest from another network first |
| wyb | Host unreachable on 80/443 | Investigate server |
| ucsc | Live JSPUI site, but no OAI path exists | Enable OAI |
| pdn (legacy) | Old `dlib.pdn.ac.lk` offline; may hold historic collection | Ask about migration status |

### Deliberate exclusions

- **SLJOL / Kelaniya WAF**: we do not attempt to circumvent bot
  protection (spoofed headers, proxies, headless browsers). Access goes
  through a formal request or not at all.
- **dspace.ac.lk (LEARN)**: near-empty pilot; revisit quarterly.
- **Private/SLIATE institutes** except SLIIT: no research repositories.

## Refreshing Everything

```bash
# 1. (optional) re-check endpoint health
python scripts/quality/validate_repositories.py

# 2. harvest per route (see registry harvest_route field)
python scripts/collection/harvest_all.py --max-records-per-target 0        # OAI targets
python scripts/collection/harvest_dspace_rest.py --id pdn                  # + nsf, busl, cmb, uwu
python scripts/collection/harvest_html_meta.py --id jfn_research           # + jfn_medicine (slow)

# 3. map, validate, export
python scripts/processing/map_to_common_schema.py --all
python scripts/quality/validate_harvested_data.py
python scripts/processing/convert_repositories_jsonl_to_csv.py
```

Do not run two harvesters for the same institution concurrently - they
write to the same raw file.
