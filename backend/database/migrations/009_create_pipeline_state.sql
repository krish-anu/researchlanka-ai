CREATE TABLE IF NOT EXISTS pipeline_state (
    state_key text PRIMARY KEY,
    last_successful_collection_date date,
    last_successful_run_id text,
    last_successful_run_at timestamptz,
    last_from_date date,
    last_records_collected integer NOT NULL DEFAULT 0,
    last_records_selected_for_db integer NOT NULL DEFAULT 0,
    last_records_loaded integer NOT NULL DEFAULT 0,
    last_raw_output text,
    last_csv_output text,
    last_db_load_output text,
    last_model_path text,
    last_db_labels text[] NOT NULL DEFAULT ARRAY[]::text[],
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS incremental_pipeline_runs (
    run_id text PRIMARY KEY,
    state_key text NOT NULL DEFAULT 'openalex_incremental',
    from_date date NOT NULL,
    to_date date NOT NULL,
    status text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    records_collected integer NOT NULL DEFAULT 0,
    records_selected_for_db integer NOT NULL DEFAULT 0,
    records_loaded integer NOT NULL DEFAULT 0,
    raw_output text,
    csv_output text,
    db_load_output text,
    model_path text,
    db_labels text[] NOT NULL DEFAULT ARRAY[]::text[],
    error text,
    CONSTRAINT incremental_pipeline_runs_status_valid
        CHECK (status IN ('succeeded', 'failed'))
);

CREATE INDEX IF NOT EXISTS idx_incremental_pipeline_runs_state_finished
    ON incremental_pipeline_runs(state_key, finished_at DESC);
