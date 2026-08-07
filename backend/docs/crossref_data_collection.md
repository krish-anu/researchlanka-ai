# Crossref Data Collection

## Added

Implemented Crossref data collection pipeline with:

- Affiliation-based publication collection
- DOI-based metadata enrichment
- Cursor pagination
- DOI duplicate filtering
- Parallel DOI retrieval
- Metadata normalization using `reduce_work()`

Main files:
 backend/src/collectors/crossref_collector.py
 backend/scripts/collection/collect_crossref.py


---

## Setup

Activate environment:

```bash
source .venv/bin/activate

pip install -r backend/requirements.txt

Run Crossref Collection
1. Inspect Crossref response
python backend/scripts/collection/collect_crossref.py inspect \
--query lanka \
--limit 3
2. Collect Sri Lankan publications

Default queries:

lanka
ceylon

Run:

python backend/scripts/collection/collect_crossref.py collect-lk

With custom queries:

python backend/scripts/collection/collect_crossref.py collect-lk \
--query lanka \
--query ceylon \
--max-records 1000

Optional:

--from-year 2000
--until-year 2026
--rows 100

Example:

python backend/scripts/collection/collect_crossref.py collect-lk \
--query lanka \
--query ceylon \
--from-year 2000 \
--until-year 2026 \
--max-records 1000

Output:

data/processed/crossref/
DOI Metadata Enrichment

Used when DOI lists are obtained from other sources such as OpenAlex.

Input:

doi_list.txt

Example:

10.xxxx/xxxxx
10.xxxx/yyyyy

Run:

python backend/scripts/collection/collect_crossref.py enrich-dois \
--doi-file doi_list.txt

With custom workers:

python backend/scripts/collection/collect_crossref.py enrich-dois \
--doi-file doi_list.txt \
--workers 20

Data Flow
Crossref API
      |
      v
Crossref Collector
      |
      v
Metadata Normalization
      |
      v
JSONL Dataset