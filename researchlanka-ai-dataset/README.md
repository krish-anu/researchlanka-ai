# ResearchLanka AI Publications Dataset v1.0

This package contains the adjudicated, distinct-work AI scholarly-publication
dataset for the ResearchLanka handover. Every retained row has
`ai_classification_label = AI` and supported Sri Lanka ownership evidence.

## Canonical Dataset

```text
data/researchlanka_ai_publications_v1.0.csv
```

This is the only publication dataset in the release package. It retains the
available abstract text and exposes 35 research-facing metadata columns. The
private application master at
`backend/data/processed/common/researchlanka_ai_publications_final.csv` retains
all 86 processing, diagnostics, and audit columns for future ResearchLanka use.

## Dataset Summary

- Rows: 3,555 distinct AI publications
- Public columns: 35
- Private master columns: 86
- Publication years: 2016-2026
- Format: CSV
- AI labels: `AI` only
- Abstracts available: 2,896 (81.46%)
- Missing abstracts: 659
- Unique OpenAlex IDs: 3,555
- Unique nonempty DOIs: 3,523
- Remaining unresolved secondary `REVIEW` decisions: 0
- Metadata corrections applied: 24

## Release Status

The technical curation is final for handover. Because this release retains
abstract text, public redistribution still requires source-rights approval and
selection of the dataset-level license under the policy in `LICENSE`; do not
make the repository public until that approval is recorded.

The final release-readiness audit also:

- adjudicated all 214 secondary AI-review rows;
- excluded 47 records whose only Sri Lanka evidence came from demonstrably
  ambiguous institution aliases;
- consolidated 95 duplicate-title/version groups, removing 107 duplicate
  versions while retaining one canonical work per group;
- excluded the Uzbek noun-classification record as non-AI and unsupported for
  Sri Lankan ownership;
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
- `audit/README.md` explains the non-dataset decision-trail files.
- `LICENSE` records the redistribution status.
- `CITATION.cff` contains citation metadata.
