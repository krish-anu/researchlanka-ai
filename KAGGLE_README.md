# ResearchLanka AI Kaggle Run Guide

This guide explains exactly how to run the ResearchLanka AI data pipeline on
Kaggle, starting from uploading the dataset and ending with downloading the
final processed files and trained model outputs.

Use this when you want to run the pipeline in Kaggle without setting up the
project locally.

## What This Kaggle Run Does

The Kaggle notebook will:

1. Clone the latest project code from GitHub.
2. Copy your uploaded dataset into the project.
3. Install the required Python and Dagster dependencies.
4. Run the no-collection preprocessing pipeline.
5. Build the cleaned final publication dataset.
6. Build model embeddings.
7. Train Logistic Regression and Linear SVM classifiers.
8. Compare model metrics.
9. Zip the outputs so you can download them from Kaggle.

The recommended notebook for your friend is:

```text
dse-project.ipynb
```

There is also a similar copy in:

```text
notebooks/kaggle_run_main_full_pipeline.ipynb
```

If both are available, use `dse-project.ipynb` because it is at the repository
root and includes extra helper cells for downloading model-only outputs.

## Before You Start

You need:

- A Kaggle account.
- Internet enabled in the Kaggle notebook.
- The raw ResearchLanka dataset uploaded as a Kaggle Dataset.
- The notebook file `dse-project.ipynb`.

The Kaggle notebook expects the uploaded dataset to contain this folder:

```text
backend/data/
```

Inside `backend/data/`, it expects the raw and already-prepared source files
used by the pipeline.

## Expected Dataset Folder Structure

When you upload the dataset to Kaggle, keep this structure:

```text
researchlanka-raw-data/
`-- backend/
    `-- data/
        |-- raw/
        |   |-- openalex/
        |   |   `-- openalex_sri_lanka_works.csv
        |   |-- sljol/
        |   |   `-- crossref_works.jsonl
        |   |-- busl/
        |   |   `-- rest_items.jsonl
        |   |-- cmb/
        |   |   `-- rest_items.jsonl
        |   |-- esn/
        |   |   `-- oai_dc.jsonl
        |   |-- nsf/
        |   |   `-- rest_items.jsonl
        |   |-- ou/
        |   |   `-- oai_dc.jsonl
        |   |-- pdn/
        |   |   `-- rest_items.jsonl
        |   |-- rjt/
        |   |   `-- oai_dc.jsonl
        |   |-- ruh/
        |   |   `-- oai_dc.jsonl
        |   |-- seu/
        |   |   `-- oai_dc.jsonl
        |   |-- sliit/
        |   |   `-- oai_dc.jsonl
        |   |-- sltc/
        |   |   `-- oai_dc.jsonl
        |   |-- uom/
        |   |   `-- oai_dc.jsonl
        |   |-- uwu/
        |   |   `-- rest_items.jsonl
        |   |-- vau/
        |   |   `-- oai_dc.jsonl
        |   `-- vpa/
        |       `-- oai_dc.jsonl
        `-- processed/
            `-- crossref/
                `-- crossref_sri_lanka_works.csv
```

Some extra files may also be present, such as JSONL, audit files, summaries, or
previous processed outputs. That is fine.

The most important point is that Kaggle must be able to find:

```text
/kaggle/input/datasets/anusankrishnathas/researchlanka-raw-data/backend/data
```

If your Kaggle dataset path is different, update `DATASET_DATA_DIR` in the first
settings cell of the notebook.

## Step 1: Prepare The Dataset Folder

On your computer, create a folder named:

```text
researchlanka-raw-data
```

Inside it, place the `backend/data` folder:

```text
researchlanka-raw-data/backend/data
```

Before uploading, check that the folder contains files like:

```text
backend/data/raw/openalex/openalex_sri_lanka_works.csv
backend/data/raw/sljol/crossref_works.jsonl
backend/data/processed/crossref/crossref_sri_lanka_works.csv
```

## Step 2: Upload The Dataset To Kaggle

1. Open Kaggle.
2. Go to **Datasets**.
3. Click **New Dataset**.
4. Upload the `researchlanka-raw-data` folder.
5. Set the dataset title to:

```text
researchlanka-raw-data
```

6. Create the dataset.
7. Wait until Kaggle finishes processing the upload.

After upload, Kaggle should expose it under a path similar to:

```text
/kaggle/input/datasets/anusankrishnathas/researchlanka-raw-data
```

Your username may be different. That is normal.

## Step 3: Create A Kaggle Notebook

1. Go to Kaggle.
2. Click **Code**.
3. Click **New Notebook**.
4. Open the notebook settings panel.
5. Turn **Internet** on.
6. Choose an accelerator only if needed. CPU is usually enough, but model
   training may run faster with more resources.

## Step 4: Add The Dataset To The Notebook

1. In the notebook right sidebar, click **Add Input**.
2. Search for your dataset:

```text
researchlanka-raw-data
```

3. Add it to the notebook.
4. Run this check in a notebook cell:

```python
!ls -la /kaggle/input
!find /kaggle/input -maxdepth 5 -type d | head -80
```

Find the real path to your uploaded `backend/data` folder.

## Step 5: Import The Project Notebook

Use this notebook from the repository:

```text
dse-project.ipynb
```

You can use it in either of these ways:

- Upload the `.ipynb` file directly to Kaggle.
- Copy the cells into a new Kaggle notebook.

If you prefer the notebook inside the `notebooks/` folder, you can use this
similar file instead:

```text
notebooks/kaggle_run_main_full_pipeline.ipynb
```

## Step 6: Check The Notebook Settings Cell

At the top of the notebook, check these values:

```python
from pathlib import Path

REPO_URL = "https://github.com/krish-anu/researchlanka-ai.git"
BRANCH = "main"
WORK_DIR = Path("/kaggle/working")
CODE_DIR = WORK_DIR / "code"
BACKEND_DIR = CODE_DIR / "backend"
DATASET_DATA_DIR = Path("/kaggle/input/datasets/anusankrishnathas/researchlanka-raw-data/backend/data")
```

If your Kaggle dataset path is different, change only this line:

```python
DATASET_DATA_DIR = Path("/kaggle/input/YOUR_REAL_DATASET_PATH/backend/data")
```

Example:

```python
DATASET_DATA_DIR = Path("/kaggle/input/researchlanka-raw-data/backend/data")
```

## Step 7: Run The Notebook From Top To Bottom

Run every cell in order.

The notebook sections are:

1. **Settings**
2. **Check Kaggle Dataset Exists**
3. **Clone Or Pull Latest Main Branch**
4. **Copy Uploaded Raw Data Into Backend**
5. **Install Dependencies**
6. **Run Dagster Pipeline Without Data Collection**
7. **Run LK Affiliation Audits**
8. **Verify Preprocessing Outputs**
9. **Build Best-Quality Embeddings**
10. **Train Best-Quality Logistic Regression**
11. **Train Best-Quality Linear SVM**
12. **Compare Models**
13. **Zip Outputs For Download**

Do not skip cells unless you know that the output already exists.

## Step 8: Confirm The Important Outputs

After the preprocessing step, the notebook should show these files:

```text
data/processed/repositories_combined.csv
data/processed/sljol.csv
data/processed/common/common_publications_final.csv
data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
```

After model training, the notebook should show files in:

```text
data/models/
```

Important model outputs include:

```text
data/models/publication_text_embeddings.parquet
data/models/logistic_regression_primary_domain.joblib
data/models/logistic_regression_primary_domain_metrics.txt
data/models/linear_svm_primary_domain.joblib
data/models/linear_svm_primary_domain_metrics.txt
data/models/classification_comparison/model_comparison.csv
```

Use `data/models/classification_comparison/model_comparison.csv` for the fair
model comparison. Those runs are trained and evaluated on the same shared
eligible row set, so the held-out row counts should match across model families.

The LK affiliation audit step should write source-specific review files in:

```text
data/reports/openalex_lk_affiliation_audit/
data/reports/crossref_lk_affiliation_audit/
```

Run both audits locally with:

```bash
cd backend
make lk-affiliation-audits PYTHON=python
```

The Crossref audit checks raw Crossref author affiliation strings and separates
strict LK authorships, multi-affiliated authorships, manual-review rows,
work-level-only evidence, and query false positives.

## Step 9: Download The Final Zip File

The final notebook cell creates:

```text
/kaggle/working/researchlanka-kaggle-outputs.zip
```

Download this file from the Kaggle output panel.

The zip file contains:

```text
data/processed/
data/models/
data/reports/
```

The most important final dataset is:

```text
data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
```

Use this file for analysis, reporting, and dashboard work.

## If Kaggle Shows Dataset Path Not Found

Run:

```python
!find /kaggle/input -maxdepth 6 -type d | sort
```

Then copy the path that ends with:

```text
backend/data
```

Update the notebook setting:

```python
DATASET_DATA_DIR = Path("PASTE_THE_CORRECT_PATH_HERE")
```

Then rerun from the dataset check cell.

## If Dependency Installation Fails

First, rerun the install cell once. Kaggle sometimes has temporary package
resolution issues.

The notebook uses a Kaggle-friendly install:

```python
!python -m pip install -r requirements.txt "protobuf<6" "google-cloud-bigquery-storage>=2.30,<3"
!python -m pip install "dagster==1.13.16" "dagster-webserver==1.13.16" "protobuf<6" "google-cloud-bigquery-storage>=2.30,<3"
!python -m pip install -e . --no-deps
!python -m pip install -e dagster-quickstart --no-deps
```

If Kaggle prints warnings but the install finishes successfully, continue.

## If Linear SVM Runs Out Of Memory

Use a smaller feature count.

Change:

```bash
--max-features 100000
```

to:

```bash
--max-features 50000
```

Then rerun the Linear SVM cell.

If it still fails, use:

```bash
--max-features 25000
```

## If You Only Need The Final Dataset

You can stop after this file is created:

```text
data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
```

You do not need to run the embeddings or model training cells unless you need
the machine learning outputs.

## Quick Checklist For Your Friend

Use this checklist when running on Kaggle:

- Upload `researchlanka-raw-data/backend/data`.
- Create a Kaggle notebook.
- Enable Internet.
- Add the uploaded dataset as notebook input.
- Upload or copy `dse-project.ipynb`.
- Check `DATASET_DATA_DIR`.
- Run all cells from top to bottom.
- Confirm the processed CSV files exist.
- Confirm OpenAlex and Crossref LK affiliation audit summaries exist.
- Confirm model metrics files exist if training was run.
- Download `/kaggle/working/researchlanka-kaggle-outputs.zip`.

## Final Output To Use

For most project work, use:

```text
common_publications_final_2016_2026_analysis_ready.csv
```

Full path inside the downloaded zip:

```text
data/processed/common/common_publications_final_2016_2026_analysis_ready.csv
```
