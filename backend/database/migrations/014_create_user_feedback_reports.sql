CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS user_feedback_reports (
    report_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_key text REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE SET NULL,
    report_type text NOT NULL,
    status text NOT NULL DEFAULT 'open',
    title text,
    detail text NOT NULL,
    reporter_name text,
    reporter_email text,
    page_url text,
    user_agent text,
    dataset_version text,
    classifier_version text,
    classifier_decision text,
    classifier_probability text,
    hard_training_example boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    resolved_at timestamptz,
    resolved_by text,
    resolution_note text,
    CONSTRAINT user_feedback_reports_type_valid CHECK (
        report_type IN (
            'incorrect_ai_classification',
            'incorrect_author',
            'incorrect_institution',
            'duplicate_publication',
            'missing_publication'
        )
    ),
    CONSTRAINT user_feedback_reports_status_valid CHECK (
        status IN ('open', 'in_review', 'resolved', 'rejected')
    )
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_reports_status_created
    ON user_feedback_reports(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_feedback_reports_publication
    ON user_feedback_reports(publication_key);

CREATE TABLE IF NOT EXISTS user_feedback_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id uuid NOT NULL REFERENCES user_feedback_reports(report_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    event_type text NOT NULL,
    actor text,
    from_status text,
    to_status text,
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_feedback_events_report_created
    ON user_feedback_events(report_id, created_at);
