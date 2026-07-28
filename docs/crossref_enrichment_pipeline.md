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

The merge uses a configurable field-level source policy with completeness as a tie-breaker inside each source.

Crossref contributes both gap-filling fields and source-specific count/reference
fields used in the count-audit sidecar and divergence flags.

## Final Output

research_lanka_dataset.parquet

research_lanka_dataset.csv
