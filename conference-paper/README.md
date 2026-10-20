# ResearchLanka AI Conference Paper

This folder is self-contained for Overleaf and produces an IEEE conference paper.

## Files

- `main.tex` — manuscript source
- `references.bib` — bibliography
- `figures/` — generated publication figures
- `generate_figures.py` — reproducible figure generator using the canonical CSV
- `main.pdf` — compiled submission draft

## Local build

```bash
python generate_figures.py
latexmk -pdf main.tex
```

## Overleaf

Upload the contents of this folder as a new project and set `main.tex` as the main document. Overleaf includes the `IEEEtran` class used by the manuscript.

Before submission, verify the target conference's exact template, anonymization policy, page-limit treatment of references, author affiliation, and required copyright or ethics statements. The present author block uses the project affiliation recorded in the repository because no university affiliation was provided.

## Reproducibility note

Figures are generated from:

```text
../researchlanka-ai-dataset/data/researchlanka_ai_publications_v1.0.csv
```

The PNG files are already included, so Overleaf does not need the dataset or Python dependencies.
