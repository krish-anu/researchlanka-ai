ALTER TABLE final_publications
    ADD COLUMN IF NOT EXISTS collected_at timestamptz,
    ADD COLUMN IF NOT EXISTS normalized_at timestamptz,
    ADD COLUMN IF NOT EXISTS classifier_version text,
    ADD COLUMN IF NOT EXISTS classifier_probability text,
    ADD COLUMN IF NOT EXISTS classifier_decision text,
    ADD COLUMN IF NOT EXISTS dataset_version text,
    ADD COLUMN IF NOT EXISTS pipeline_version text;

CREATE INDEX IF NOT EXISTS idx_final_publications_dataset_version
    ON final_publications(dataset_version);

UPDATE final_publications
SET collected_at = COALESCE(collected_at, source_datestamp),
    normalized_at = COALESCE(normalized_at, loaded_at),
    classifier_version = COALESCE(classifier_version, ai_classification_model),
    classifier_probability = COALESCE(classifier_probability, ai_classification_confidence),
    classifier_decision = COALESCE(classifier_decision, ai_classification_label),
    dataset_version = COALESCE(dataset_version, 'researchlanka-' || CURRENT_DATE::text),
    pipeline_version = COALESCE(pipeline_version, 'pipeline-v1.4.2');

CREATE OR REPLACE VIEW public_eligible_publications AS
SELECT
    p.*,
    r.review_status,
    COALESCE(r.decided_by_email, r.decided_by_name, r.assigned_reviewer_email) AS reviewed_by,
    r.decision_timestamp AS reviewed_at
FROM final_publications p
JOIN ai_review_records r ON r.publication_key = p.publication_key
WHERE p.retired_at IS NULL
  AND r.review_status IN ('auto_accepted', 'human_accepted')
  AND upper(coalesce(p.ownership_decision, '')) = 'INCLUDE'
  AND upper(coalesce(p.ownership_confidence, '')) IN ('HIGH', 'MEDIUM')
  AND lower(coalesce(p.needs_manual_review, 'false')) NOT IN ('true', '1', 'yes');

CREATE OR REPLACE VIEW accepted_ai_publications AS
SELECT *
FROM public_eligible_publications;
