# ResearchLanka AI Publications Dataset v1.0

This package contains a draft public-release dataset of AI-related scholarly publications connected to Sri Lanka.

## Files

```text
data/researchlanka_ai_publications_v1.0.csv
data/researchlanka_ai_publications_v1.0.parquet
README.md
DATA_DICTIONARY.md
METHODOLOGY.md
QUALITY_REPORT.md
LICENSE
CITATION.cff
CHANGELOG.md
checksums.sha256
```

## Dataset Summary

- Rows: 4,177 AI-classified publications
- Columns: 66
- Publication years: 2016-2026
- Format: CSV and Parquet
- AI label included in release: `AI`
- Classifier: ResearchLanka AI relevance Linear SVM
- Mean AI confidence score: 0.7504

## Important Release Status

This package is structurally ready for public dataset publication, but the current contents should be treated as a release candidate until the remaining human checks are complete.

Known release-readiness items:

- 2 records have blank titles.
- 203 duplicate candidates require manual review.
- A 500-record human audit sample has been prepared separately at `backend/data/processed/ai/final_ai_corpus_human_audit_sample.csv`.
- Final publication should wait until AI relevance and Sri Lanka relevance labels in the audit sample are completed and summarized.

## Recommended Citation

Use the metadata in `CITATION.cff`. Update the authors, DOI, repository URL, and release date before depositing the final public version.

## Loading The Dataset

Python:

```python
import pandas as pd

df = pd.read_csv("data/researchlanka_ai_publications_v1.0.csv")
# or
df = pd.read_parquet("data/researchlanka_ai_publications_v1.0.parquet")
```

## Documentation

- `DATA_DICTIONARY.md` describes each column.
- `METHODOLOGY.md` explains collection, cleaning, Sri Lanka relevance processing, deduplication, and AI classification.
- `QUALITY_REPORT.md` summarizes current validation gates and remaining publication blockers.
- `LICENSE` documents the current redistribution status.

