# Metadata Quality Report Index

This report set documents metadata quality, cleaning decisions, and interpretation limits for OpenAlex, Crossref, and Local repository metadata.

| Task | Document | Notebook(s) | Output folder |
|------|----------|-------------|---------------|
| Analyze missing values | [03_missing_values_analysis.md](03_missing_values_analysis.md) | 01, 02, 03 | `notebooks/outputs/notebook01–03/` |
| Analyze metadata completeness | [04_metadata_completeness_analysis.md](04_metadata_completeness_analysis.md) | 02 | `notebooks/outputs/notebook02/` |
| Identify conflicting metadata | [05_conflicting_metadata_analysis.md](05_conflicting_metadata_analysis.md) | **04** | `notebooks/outputs/notebook04/` |
| Field-level data-quality statistics | [06_field_level_data_quality.md](06_field_level_data_quality.md) | 02, 03, **04** | `notebooks/outputs/notebook04/` |
| Final 26-column dataset decisions | [07_last_26_columns_final_dataset_decisions.md](07_last_26_columns_final_dataset_decisions.md) | `scripts/analysis/columns/analyze_final_26_columns.py` | `data/reports/column_analysis/` |
| Column 26-50 dataset decisions | [08_columns_26_50_final_dataset_decisions.md](08_columns_26_50_final_dataset_decisions.md) | `scripts/analysis/columns/analyze_second_25_columns.py` | `data/reports/column_analysis/` |
| Column 1-25 dataset decisions | [09_columns_1_25_final_dataset_decisions.md](09_columns_1_25_final_dataset_decisions.md) | `scripts/analysis/columns/analyze_first_25_columns.py` | `data/reports/column_analysis/` |
| Institution, affiliation and country standardization | [10_institution_and_affiliation_standardization.md](10_institution_and_affiliation_standardization.md) | `src/pipeline/build_institution_normalized_dataset.py` | `data/processed/common/` |
| Publication type and venue standardization | [11_publication_type_and_venue_standardization.md](11_publication_type_and_venue_standardization.md) | `src/pipeline/build_type_journal_normalized_dataset.py` | `data/processed/common/` |

## Running the pipeline

[PIPELINE_RUNBOOK.md](PIPELINE_RUNBOOK.md) — every command, in order, from a clean checkout to a loaded database.

## Working on the code

[INSTITUTION_CODE_WALKTHROUGH.md](INSTITUTION_CODE_WALKTHROUGH.md) — how the institution, affiliation and collaboration code fits together: what each function does, recipes for common changes, and the invariants that break silently.

## Notebooks

1. `notebooks/01_Dataset_Overview_and_Corpus_Profiling.ipynb` — corpus profile, DOI gaps by type/institute  
2. `notebooks/02_metadata_completeness_analysis.ipynb` — completeness matrix + playbook  
3. `notebooks/03_cross_source_metadata_analysis.ipynb` — overlap + enrichment fill opportunities  
4. `notebooks/04_conflict_and_data_quality_analysis.ipynb` — conflicts + DQ scorecard  

## One-line verdict

OpenAlex is a strong analytical backbone, while Crossref and Local sources add important DOI, publisher, and national provenance evidence. The implemented merge uses configurable field-level source policy, conflict logging, count audit sidecars, and citation/reference divergence flags. Published findings should still disclose the limitations in [11_metadata_quality_limitations.md](11_metadata_quality_limitations.md).
