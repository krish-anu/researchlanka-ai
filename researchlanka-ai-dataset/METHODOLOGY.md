# Methodology

## Scope

The dataset contains final-curated AI-related scholarly publications with
evidence of a Sri Lanka connection. It contains AI publications only.

## Source Collection

Records were assembled from multiple scholarly metadata sources used by the ResearchLanka pipeline, including OpenAlex, Crossref, SLJOL, and institutional repository harvests. Source provenance is retained in `source_dataset`, `source_institution_id`, and `source_record_id`.

## Common Schema Processing

Source records were mapped into a common publication schema. The pipeline normalizes identifiers, publication dates, author and institution fields, source metadata, open-access metadata, topics, concepts, and publication-type fields where available.

## Sri Lanka Relevance

The pipeline stores Sri Lanka relevance evidence in fields such as `sri_lankan_authors`, `sri_lankan_institutions`, `countries`, `ownership_decision`, `ownership_class`, `ownership_confidence`, `ownership_reason`, and `ownership_evidence`.

Rows still marked `needs_manual_review = true` should not be published as final. The current release validation found no such rows in the AI-only dataset.

## Deduplication

The upstream dataset was deduplicated before AI-only filtering. Release
validation also checks for residual duplicates and publication versions using:

- OpenAlex ID
- DOI
- normalized title plus publication year

The release-readiness audit reviewed 95 connected exact/normalized-title groups
covering 202 identifiers. It retained one canonical research work per group and
removed 107 preprint, repository, supplement, malformed-DOI, or alternate
version records. The final dataset has no duplicate OpenAlex IDs, DOI values,
normalized titles, or normalized title/year keys.

## AI Relevance Classification

The final corpus combines records resolved by the A2 title/abstract/keywords
model, the legacy linear SVM, Gemini-assisted review, and finished human review.
The `ai_classification_model`, `ai_classification_reason`, and
`final_resolution_source` fields preserve row-level provenance. Absolute local
paths were replaced with portable model identifiers during final curation.

Current production acceptance uses a three-way decision:

```text
AUTO_AI / REVIEW / AUTO_NON_AI
```

Deprecated LLM-label self-evaluation runs are no longer reported as project
benchmarks because they measured reproduction of generated labels rather than
agreement with independent human judgement.

The release contains only rows where `ai_classification_label = AI`. All 214
secondary `REVIEW` records were adjudicated: 203 were retained as AI, five were
excluded for unsupported Sri Lanka ownership, five were removed as duplicate
versions, and one was excluded as both non-AI and unsupported for ownership.
These are operational release decisions, not an independently blinded academic
benchmark.

## Human Verification

A later curation pass partitioned the previous 4,058-row AI candidate export
into a 3,706-row release candidate and 352 excluded non-AI records. The final
release-readiness audit then removed 151 unique rows from that candidate: 47
unsupported Sri Lanka matches, 107 duplicate versions, and one non-AI record,
with overlaps between those categories. The resulting distinct-work release
contains 3,555 rows. Twenty-four supplied metadata corrections were also
applied.

## Abstract Policy

The release retains the available `abstract` and `abstract_search_text` values;
2,896 of 3,555 records have an abstract and 659 remain blank because no abstract
was obtained. The `abstract_missing_flag` describes availability per record.
Because source-level redistribution rights are not consistently recorded, the
package must not be made public until the rights and dataset-license review in
`LICENSE` is completed.

## Public Schema Policy

The public CSV contains 35 research-facing fields covering publication
identifiers, bibliographic metadata, abstracts and keywords, authors and
institutions, research categories, source licensing, open-access status, and
the final AI label. The private 86-column master additionally retains model
scores and identifiers, review provenance, ownership diagnostics, normalized
search fields, missing-value flags, and collection-processing fields. Those
internal columns remain available for reproducibility and future processing but
are not distributed in the main public CSV.

An earlier 500-row stratified sample was manually verified. Its decisions were
superseded by the final full-corpus curation; the intermediate audit dataset was
removed from the handover workspace to prevent it being mistaken for the final
publication corpus.

Review fields used by that audit are:

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
Guideline version: ai-relevance-annotation-v1.1
Annotators: record count and overlap count
Blinding: whether model predictions/confidence/reasoning were hidden
Agreement: percent agreement and Cohen's kappa on overlapping labels
Adjudication: process for disagreements and REVIEW cases
Final benchmark label: adjudicated AI/NON_AI label
```

Each reviewed row should record `label`, `confidence`, `evidence_span`,
`reason`, and `ambiguous_flag`. Annotators should complete first-pass labels
independently before seeing model predictions or confidence scores.

Detailed protocol:

```text
backend/docs/AI_RELEVANCE_ANNOTATION_PROTOCOL.md
```
