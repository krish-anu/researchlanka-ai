ALTER TABLE ai_review_records
    ADD COLUMN IF NOT EXISTS hard_negative boolean NOT NULL DEFAULT false,
    ADD COLUMN IF NOT EXISTS hard_negative_category text,
    ADD COLUMN IF NOT EXISTS hard_negative_evidence text;

CREATE INDEX IF NOT EXISTS idx_ai_review_records_hard_negative
    ON ai_review_records(hard_negative, decision_timestamp DESC)
    WHERE hard_negative IS TRUE;

UPDATE ai_review_records
SET hard_negative = true,
    hard_negative_category = COALESCE(hard_negative_category, 'human_rejected_model_ai'),
    hard_negative_evidence = NULLIF(reviewer_notes, '')
WHERE review_status = 'human_rejected'
  AND lower(replace(coalesce(original_ai_label, ''), '_', '-')) IN (
      'ai',
      'ai-related',
      'artificial intelligence',
      'artificial-intelligence'
  );
