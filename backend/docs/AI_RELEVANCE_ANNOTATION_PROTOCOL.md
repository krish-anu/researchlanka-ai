# AI Relevance Human Annotation Protocol

This protocol defines how human AI-relevance labels should be produced,
audited, and reported for ResearchLanka AI relevance model evaluation.

## Purpose

Human labels are used in two different ways:

| Label set type | Purpose | Benchmark claim |
| --- | --- | --- |
| Operational human-verified labels | Resolve uncertain cases and improve the production dataset | Useful for curation and model improvement |
| Blinded benchmark labels | Estimate stable model performance | Suitable for reported benchmark metrics |

Current project labels should be treated as operational human-verified labels
unless the batch explicitly records independent annotators, blinding, agreement,
and adjudication.

## Label Definitions

Use only publication metadata available in the review sheet: title, abstract,
keywords, topics, concepts, and related subject metadata.

| Label | Definition |
| --- | --- |
| `AI` | AI, machine learning, deep learning, NLP, computer vision, robotics AI, generative AI, expert systems, reinforcement learning, or related AI methods are central to the publication objective, method, application, evaluation, or main subject. |
| `NON_AI` | The publication does not contain enough evidence that AI is central or substantial. General computing, sensors, software, statistics, fuzzy decision-making, optimization, automation, forecasting, or "smart" terminology is not enough by itself. |
| `REVIEW` | Evidence is insufficient, conflicting, or ambiguous. The record should not be automatically accepted as AI or rejected as NON_AI without adjudication. |

`REVIEW` is a workflow state, not a final positive label. For binary model
evaluation, `REVIEW` records must either be excluded with a stated rule or
resolved to `AI`/`NON_AI` by adjudication.

## Required Reporting Fields

Every human-labelled benchmark or audit batch should report:

| Field | Required value |
| --- | --- |
| Guideline version | Example: `ai-relevance-annotation-v1.0` |
| Review date range | Start and end dates |
| Number of records | Total reviewed rows |
| Sampling design | Informative, corpus-representative, AI-heavy, hard-negative, or other |
| Number of independent annotators | Count of annotators who labelled the same record before adjudication |
| Annotator blinding | Whether model labels, confidence scores, and LLM reasoning were hidden |
| Inter-annotator agreement | Percent agreement and Cohen's kappa when two annotators overlap |
| Adjudication procedure | How disagreements and `REVIEW` cases were resolved |
| Post-error label changes | Whether labels changed after observing model errors |
| Final label column | The column used as the benchmark label |

## Recommended Benchmark Procedure

1. Prepare a labelled batch with stable record IDs.
2. Hide model predictions, confidence scores, Gemini reasoning, and previous
   model-error notes from annotators during first-pass labelling.
3. Have at least two annotators independently label a shared subset, preferably
   100-200 records or at least 20 percent of the benchmark batch.
4. Compute percent agreement and Cohen's kappa on the overlapping subset.
5. Send disagreements and all `REVIEW` records to adjudication.
6. Store both first-pass labels and final adjudicated labels.
7. Report model metrics only against the final adjudicated benchmark label.

Agreement can be calculated with:

```bash
cd backend
python scripts/ai_relevance/evaluate_annotation_agreement.py \
  --input data/processed/ai/annotation_overlap.csv \
  --annotator-a annotator_1_ai_label \
  --annotator-b annotator_2_ai_label \
  --output data/reports/ai_annotation_agreement.json
```

Use `--include-review` only when `REVIEW` should be scored as a third class.
For binary AI-vs-NON_AI benchmark reporting, leave `REVIEW` excluded and state
how those rows were adjudicated.

## Current Project Status

The project has human-reviewed data from audit and review batches, including
AI-heavy and uncertainty-focused samples. These labels are valuable for
training, calibration, false-positive analysis, and production curation.

However, unless a batch records independent annotator overlap, blinding,
agreement, adjudication, and guideline version, it should not be described as a
fully stable blinded benchmark. It should be described as human-verified
operational data.

## Treatment of Label Updates

Model-error review may reveal mistaken labels or unclear guideline boundaries.
When labels are changed after model-error inspection:

- record the previous label;
- record the corrected label;
- record the reason for correction;
- mark the row as post-adjudication or post-error-review;
- do not treat the corrected label as an independent blinded first-pass label.

## Minimum Report Text

Use this wording for current model reports when full annotation metadata is not
available:

```text
Human labels were used for operational verification, calibration, and model
selection. The available review batches do not consistently record independent
annotator counts, blinding, inter-annotator agreement, adjudication status, or
guideline version. Therefore, these labels are treated as human-verified
operational labels rather than a fully blinded benchmark. Future benchmark
reporting should include annotator overlap, Cohen's kappa, adjudication records,
and explicit handling of REVIEW cases.
```
