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

AI relevance was assigned using the ResearchLanka AI relevance Linear SVM classifier trained on LLM-labelled publication metadata. The model was trained using title, abstract, keywords, topics, concepts, primary topic, primary subfield, primary field, and primary domain text.

Training summary from the current model artifact:

- Training labels: `AI`, `NON_AI`
- Usable labelled rows: 4,437
- Test rows: 888
- Accuracy: 0.9595
- Macro F1: 0.9552
- AI precision: 0.94
- AI recall: 0.94

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

