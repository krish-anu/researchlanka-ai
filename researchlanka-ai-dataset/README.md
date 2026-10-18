# ResearchLanka AI Publications Dataset v1.0

This package contains the final curated AI-only scholarly-publication dataset
for the ResearchLanka handover. Every row has
`ai_classification_label = AI` and Sri Lanka ownership evidence.

## Canonical Dataset

```text
data/researchlanka_ai_publications_v1.0.csv
```

This is the only dataset file in the public package. The backend runtime mirror
is `backend/data/processed/common/researchlanka_ai_publications_final.csv`.
Both files must remain byte-identical.

## Dataset Summary

- Rows: 3,706 AI publications
- Columns: 86
- Publication years: 2016-2026
- Format: CSV
- AI labels: `AI` only
- Abstracts available: 3,013
- Unique OpenAlex IDs: 3,706
- Non-AI records removed during final curation: 352
- Metadata corrections applied: 24

## Release Status

The data curation is final for handover. Public redistribution still requires
approval under the policy in `LICENSE`; do not upload the package to a public
dataset host until that approval is recorded.

The final curation also:

- removed the 352 records classified as non-AI;
- applied 24 supplied abstract/keyword corrections;
- recalculated title, abstract, and keyword search-helper fields;
- removed absolute workstation paths from model identifiers; and
- removed obsolete CSV and Parquet copies from the handover package.

## Loading

```python
import pandas as pd

df = pd.read_csv("data/researchlanka_ai_publications_v1.0.csv")
```

## Documentation

- `DATA_DICTIONARY.md` describes the columns.
- `METHODOLOGY.md` explains collection and final curation.
- `QUALITY_REPORT.md` records validation results.
- `LICENSE` records the redistribution status.
- `CITATION.cff` contains citation metadata.
