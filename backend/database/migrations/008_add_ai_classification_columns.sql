ALTER TABLE final_publications
    ADD COLUMN IF NOT EXISTS ai_classification_label text,
    ADD COLUMN IF NOT EXISTS ai_classification_confidence text,
    ADD COLUMN IF NOT EXISTS ai_classification_model text,
    ADD COLUMN IF NOT EXISTS ai_classification_reason text;

ALTER TABLE final_publications
    DROP CONSTRAINT IF EXISTS final_publications_ai_classification_label_valid;

ALTER TABLE final_publications
    ADD CONSTRAINT final_publications_ai_classification_label_valid
        CHECK (
            ai_classification_label IS NULL
            OR ai_classification_label IN ('AI', 'non-AI', 'review')
        );
