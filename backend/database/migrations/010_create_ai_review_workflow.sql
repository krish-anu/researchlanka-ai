CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS ai_review_records (
    publication_key text PRIMARY KEY REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE CASCADE,
    original_ai_label text,
    original_ai_confidence text,
    original_ai_model text,
    original_ai_reason text,
    normalized_ai_label text,
    normalized_ai_confidence text,
    review_status text NOT NULL DEFAULT 'pending_review',
    acceptance_method text,
    assigned_reviewer_id text,
    assigned_reviewer_email text,
    assigned_reviewer_name text,
    assigned_at timestamptz,
    decided_by_id text,
    decided_by_email text,
    decided_by_name text,
    reviewer_notes text NOT NULL DEFAULT '',
    decision_timestamp timestamptz,
    record_version integer NOT NULL DEFAULT 1,
    sync_status text NOT NULL DEFAULT 'not_queued',
    sync_attempt_count integer NOT NULL DEFAULT 0,
    last_sync_error text,
    last_synced_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ai_review_records_status_valid CHECK (
        review_status IN (
            'pending_review',
            'auto_accepted',
            'human_accepted',
            'human_rejected'
        )
    ),
    CONSTRAINT ai_review_records_method_valid CHECK (
        acceptance_method IS NULL OR acceptance_method IN ('auto', 'human')
    ),
    CONSTRAINT ai_review_records_confidence_valid CHECK (
        normalized_ai_confidence IS NULL
        OR normalized_ai_confidence IN ('HIGH', 'MEDIUM', 'LOW', 'UNRECOGNIZED')
    ),
    CONSTRAINT ai_review_records_sync_status_valid CHECK (
        sync_status IN ('not_queued', 'pending', 'succeeded', 'failed')
    )
);

CREATE INDEX IF NOT EXISTS idx_ai_review_records_status
    ON ai_review_records(review_status);
CREATE INDEX IF NOT EXISTS idx_ai_review_records_assignee_status
    ON ai_review_records(assigned_reviewer_email, review_status, publication_key);
CREATE INDEX IF NOT EXISTS idx_ai_review_records_sync_status
    ON ai_review_records(sync_status, updated_at);

CREATE TABLE IF NOT EXISTS ai_review_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_key text NOT NULL REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE CASCADE,
    event_type text NOT NULL,
    actor_id text,
    actor_email text,
    actor_name text,
    from_status text,
    to_status text,
    from_reviewer_email text,
    to_reviewer_email text,
    notes text NOT NULL DEFAULT '',
    record_version integer,
    idempotency_key text UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ai_review_events_publication_key
    ON ai_review_events(publication_key, created_at);

CREATE TABLE IF NOT EXISTS ai_review_sync_jobs (
    job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_key text NOT NULL REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE CASCADE,
    job_type text NOT NULL DEFAULT 'sync_record',
    target_record_version integer NOT NULL,
    status text NOT NULL DEFAULT 'pending',
    attempts integer NOT NULL DEFAULT 0,
    next_attempt_at timestamptz NOT NULL DEFAULT now(),
    locked_at timestamptz,
    locked_by text,
    last_error text,
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ai_review_sync_jobs_status_valid CHECK (
        status IN ('pending', 'running', 'succeeded', 'failed')
    ),
    CONSTRAINT ai_review_sync_jobs_type_valid CHECK (
        job_type IN ('sync_record', 'reconcile', 'snapshot')
    )
);

CREATE INDEX IF NOT EXISTS idx_ai_review_sync_jobs_claim
    ON ai_review_sync_jobs(status, next_attempt_at, created_at);
CREATE INDEX IF NOT EXISTS idx_ai_review_sync_jobs_publication_key
    ON ai_review_sync_jobs(publication_key, target_record_version);

CREATE OR REPLACE VIEW accepted_ai_publications AS
SELECT p.*
FROM final_publications p
JOIN ai_review_records r ON r.publication_key = p.publication_key
WHERE r.review_status IN ('auto_accepted', 'human_accepted');
