CREATE TABLE data_sources (
    source_id TEXT PRIMARY KEY,
    source_name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    adapter_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE source_configurations (
    configuration_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES data_sources(source_id),
    version TEXT NOT NULL,
    configuration_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE collection_runs (
    run_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES data_sources(source_id),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,
    records_collected INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE TABLE source_records (
    source_record_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES data_sources(source_id),
    external_identifier TEXT,
    raw_record JSONB NOT NULL,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    adapter_version TEXT,
    mapping_version TEXT,
    processing_status TEXT NOT NULL
);

CREATE TABLE institutions (
    institution_id TEXT PRIMARY KEY,
    preferred_name TEXT NOT NULL,
    country_code TEXT NOT NULL,
    ror_id TEXT,
    parent_institution_id TEXT REFERENCES institutions(institution_id),
    institution_type TEXT
);

CREATE TABLE institution_aliases (
    alias_id BIGSERIAL PRIMARY KEY,
    institution_id TEXT NOT NULL REFERENCES institutions(institution_id),
    alternative_name TEXT NOT NULL
);

CREATE TABLE publications (
    publication_id TEXT PRIMARY KEY,
    doi TEXT,
    title TEXT NOT NULL,
    normalized_title TEXT,
    abstract TEXT,
    publication_year INTEGER,
    publication_date DATE,
    publication_type TEXT,
    language TEXT,
    journal TEXT,
    publisher TEXT,
    citation_count INTEGER,
    open_access_status TEXT,
    source_url TEXT,
    national_association BOOLEAN NOT NULL DEFAULT FALSE,
    collaboration_type TEXT,
    source_specific_metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE publication_source_records (
    publication_id TEXT NOT NULL REFERENCES publications(publication_id),
    source_record_id TEXT NOT NULL REFERENCES source_records(source_record_id),
    PRIMARY KEY (publication_id, source_record_id)
);

CREATE TABLE authors (
    author_id TEXT PRIMARY KEY,
    preferred_name TEXT NOT NULL,
    orcid TEXT,
    openalex_id TEXT,
    resolution_status TEXT NOT NULL DEFAULT 'unresolved'
);

CREATE TABLE publication_authors (
    publication_id TEXT NOT NULL REFERENCES publications(publication_id),
    author_id TEXT NOT NULL REFERENCES authors(author_id),
    author_position INTEGER,
    PRIMARY KEY (publication_id, author_id)
);

CREATE TABLE publication_institutions (
    publication_id TEXT NOT NULL REFERENCES publications(publication_id),
    institution_id TEXT NOT NULL REFERENCES institutions(institution_id),
    PRIMARY KEY (publication_id, institution_id)
);

CREATE TABLE collaboration_edges (
    edge_id BIGSERIAL PRIMARY KEY,
    source_entity TEXT NOT NULL,
    target_entity TEXT NOT NULL,
    edge_type TEXT NOT NULL,
    publication_id TEXT REFERENCES publications(publication_id)
);

CREATE TABLE data_quality_reports (
    report_id TEXT PRIMARY KEY,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    report_json JSONB NOT NULL
);

CREATE TABLE duplicate_candidates (
    candidate_id BIGSERIAL PRIMARY KEY,
    left_source_record_id TEXT,
    right_source_record_id TEXT,
    match_type TEXT NOT NULL,
    confidence TEXT NOT NULL,
    merge_decision TEXT NOT NULL
);

CREATE TABLE model_predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    publication_id TEXT NOT NULL REFERENCES publications(publication_id),
    model_name TEXT NOT NULL,
    model_version TEXT NOT NULL,
    prediction_type TEXT NOT NULL,
    prediction_value JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
