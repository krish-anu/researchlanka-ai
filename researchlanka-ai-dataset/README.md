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
- Classifier recorded in this package: legacy ResearchLanka linear SVM. The
  checked-in production manifest now selects the newer A2 XGBoost model, so
  this package must be regenerated before it can represent the current model.

## Important Release Status

This package is structurally ready for public dataset publication, but the current contents should be treated as a release candidate until the remaining human checks are complete.

Known release-readiness items:

- 2 records have blank titles.
- 203 duplicate candidates require manual review.
- A 500-record operational human audit was completed on this exact package:
  441 records were confirmed AI and 59 were labelled non-AI; 492 were
  confirmed Sri Lanka relevant and 8 were labelled not Sri Lanka relevant.
- Those audit findings have not yet been propagated into this package (the AI
  and Sri Lanka findings may overlap), and the audit was operational rather
  than an independently blinded benchmark.
- Final publication must wait until the corrections are applied, the current
  production model output is re-audited, and redistribution licensing is
  approved.

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
