# Methodology

## Scope

The dataset is intended to contain AI-related scholarly publications with evidence of a Sri Lanka connection. The current package is a v1.0 release candidate and should be finalized after human audit labels are completed.

## Source Collection

Records were assembled from multiple scholarly metadata sources used by the ResearchLanka pipeline, including OpenAlex, Crossref, SLJOL, and institutional repository harvests. Source provenance is retained in `source_dataset`, `source_institution_id`, and `source_record_id`.

## Common Schema Processing

Source records were mapped into a common publication schema. The pipeline normalizes identifiers, publication dates, author and institution fields, source metadata, open-access metadata, topics, concepts, and publication-type fields where available.

## Sri Lanka Relevance

The pipeline stores Sri Lanka relevance evidence in fields such as `sri_lankan_authors`, `sri_lankan_institutions`, `countries`, `ownership_decision`, `ownership_class`, `ownership_confidence`, `ownership_reason`, and `ownership_evidence`.

Rows still marked `needs_manual_review = true` should not be published as final. The current release validation found no such rows in the AI-only dataset.

## Deduplication

The upstream dataset was deduplicated before AI-only filtering. Release validation also checks for possible residual duplicates using:

- OpenAlex ID
- DOI
- normalized title plus publication year

The current release candidate contains 203 duplicate candidates requiring manual review. These are candidate collisions, not automatic confirmed duplicates.

## AI Relevance Classification

The current production AI relevance decision is based on the ResearchLanka A1
XGBoost model using title and abstract text, with sigmoid calibration enabled.
Production acceptance uses a three-way decision:

```text
AUTO_AI / REVIEW / AUTO_NON_AI
```

Deprecated LLM-label self-evaluation runs are no longer reported as project
benchmarks because they measured reproduction of generated labels rather than
agreement with independent human judgement.

The release contains rows where `ai_classification_label = AI`.

## Human Verification

A separate 500-row random sample from the final AI corpus was generated for manual verification:

```text
backend/data/processed/ai/final_ai_corpus_human_audit_sample.csv
```

Before final publication, reviewers should fill:

- `human_ai_label`: `AI`, `NON_AI`, or `REVIEW`
- `human_lk_relevance_label`: `VALID_LK`, `NOT_LK`, or `REVIEW`
- `human_notes`: optional notes

The final publication report should include AI relevance precision and Sri Lanka relevance precision estimated from this sample.

## Human Annotation Protocol

Human labels are treated differently depending on how they were produced:

| Label set type | Use |
| --- | --- |
| Human-verified operational labels | Dataset curation, uncertain-case resolution, calibration, and model improvement |
| Blinded benchmark labels | Stable model-performance reporting |

For a human-labelled batch to support benchmark claims, the report should record
the number of independent annotators, whether annotators were blinded to model
predictions and confidence scores, inter-annotator agreement, adjudication
procedure, guideline version, post-error label changes, and the treatment of
ambiguous `REVIEW` cases.

The current release-candidate documentation does not consistently record all of
these fields for every historical review batch. Therefore, those labels should
be described as human-verified operational labels unless the batch explicitly
documents independent blinded annotation and adjudication.

Recommended benchmark reporting:

```text
Guideline version: ai-relevance-annotation-v1.0
Annotators: record count and overlap count
Blinding: whether model predictions/confidence/reasoning were hidden
Agreement: percent agreement and Cohen's kappa on overlapping labels
Adjudication: process for disagreements and REVIEW cases
Final benchmark label: adjudicated AI/NON_AI label
```

Detailed protocol:

```text
backend/docs/AI_RELEVANCE_ANNOTATION_PROTOCOL.md
```
