# Crossref Enrichment Pipeline

## Step 1

Collect Sri Lankan publications from OpenAlex.

Output:

openalex.csv

## Step 2

Extract valid DOIs.

## Step 3

Query Crossref using DOI endpoint.

GET /works/{doi}

## Step 4

Normalize Crossref metadata.

## Step 5

Merge with OpenAlex.

OpenAlex remains source of truth.

Crossref only fills missing fields.

## Final Output

research_lanka_dataset.parquet

research_lanka_dataset.csv