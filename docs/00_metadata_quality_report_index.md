# Metadata Quality Report Index

This report set finalizes four analysis tasks using OpenAlex, Crossref, and Local repository metadata.

| Task | Document | Notebook(s) | Output folder |
|------|----------|-------------|---------------|
| Analyze missing values | [03_missing_values_analysis.md](03_missing_values_analysis.md) | 01, 02, 03 | `notebooks/outputs/notebook01–03/` |
| Analyze metadata completeness | [04_metadata_completeness_analysis.md](04_metadata_completeness_analysis.md) | 02 | `notebooks/outputs/notebook02/` |
| Identify conflicting metadata | [05_conflicting_metadata_analysis.md](05_conflicting_metadata_analysis.md) | **04** | `notebooks/outputs/notebook04/` |
| Field-level data-quality statistics | [06_field_level_data_quality.md](06_field_level_data_quality.md) | 02, 03, **04** | `notebooks/outputs/notebook04/` |

## Notebooks

1. `notebooks/01_Dataset_Overview_and_Corpus_Profiling.ipynb` — corpus profile, DOI gaps by type/institute  
2. `notebooks/02_metadata_completeness_analysis.ipynb` — completeness matrix + playbook  
3. `notebooks/03_cross_source_metadata_analysis.ipynb` — overlap + enrichment fill opportunities  
4. `notebooks/04_conflict_and_data_quality_analysis.ipynb` — conflicts + DQ scorecard  

## One-line verdict

OpenAlex is a reliable source of truth for identity and analytics fields; Crossref/Local should **fill missing values** (abstract, ORCID, venue gaps, keywords, funding, events) rather than overwrite OA core fields; treat publisher/journal string disagreements as naming variants; store citation counts from both sources with a divergence flag.
