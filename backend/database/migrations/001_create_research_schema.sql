CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS countries (
    country_code text PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE IF NOT EXISTS institutions (
    institution_id text PRIMARY KEY,
    country_code text NOT NULL REFERENCES countries(country_code)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    parent_institution_id text REFERENCES institutions(institution_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    preferred_name text NOT NULL,
    ror_id text UNIQUE,
    institution_type text
);

CREATE TABLE IF NOT EXISTS institution_aliases (
    alias_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    institution_id text NOT NULL REFERENCES institutions(institution_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    alias_name text NOT NULL,
    CONSTRAINT institution_aliases_unique_alias
        UNIQUE (institution_id, alias_name)
);

CREATE TABLE IF NOT EXISTS data_sources (
    source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name text NOT NULL UNIQUE,
    source_type text NOT NULL
);

CREATE TABLE IF NOT EXISTS source_records (
    source_record_uuid uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid NOT NULL REFERENCES data_sources(source_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    source_institution_id text REFERENCES institutions(institution_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    source_record_id text NOT NULL,
    source_datestamp timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT source_records_unique_source_record
        UNIQUE (source_id, source_record_id)
);

CREATE TABLE IF NOT EXISTS venues (
    venue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_name text NOT NULL,
    venue_type text,
    publisher text,
    issn text,
    issn_l text
);

CREATE TABLE IF NOT EXISTS publications (
    publication_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    venue_id uuid REFERENCES venues(venue_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    doi text UNIQUE,
    openalex_id text UNIQUE,
    title text NOT NULL,
    subtitle text,
    abstract text,
    publication_year integer,
    publication_date date,
    publication_type text,
    language text,
    citation_count integer,
    reference_count integer,
    is_oa boolean,
    oa_status text,
    landing_page_url text,
    pdf_url text,
    CONSTRAINT publications_year_valid
        CHECK (publication_year IS NULL OR publication_year BETWEEN 1500 AND 2100),
    CONSTRAINT publications_citation_count_nonnegative
        CHECK (citation_count IS NULL OR citation_count >= 0),
    CONSTRAINT publications_reference_count_nonnegative
        CHECK (reference_count IS NULL OR reference_count >= 0)
);

CREATE TABLE IF NOT EXISTS publication_sources (
    publication_source_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    source_record_uuid uuid NOT NULL REFERENCES source_records(source_record_uuid)
        ON UPDATE CASCADE ON DELETE CASCADE,
    source_priority integer NOT NULL DEFAULT 0,
    is_primary_source boolean NOT NULL DEFAULT false,
    CONSTRAINT publication_sources_unique_source
        UNIQUE (publication_id, source_record_uuid)
);

CREATE TABLE IF NOT EXISTS authors (
    author_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    display_name text NOT NULL,
    orcid text UNIQUE
);

CREATE TABLE IF NOT EXISTS publication_authors (
    publication_author_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    author_id uuid NOT NULL REFERENCES authors(author_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    author_position integer,
    raw_author_name text,
    is_corresponding boolean NOT NULL DEFAULT false,
    is_sri_lankan_author boolean NOT NULL DEFAULT false,
    CONSTRAINT publication_authors_position_positive
        CHECK (author_position IS NULL OR author_position > 0),
    CONSTRAINT publication_authors_unique_position
        UNIQUE (publication_id, author_position)
);

CREATE TABLE IF NOT EXISTS author_affiliations (
    affiliation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_author_id uuid NOT NULL
        REFERENCES publication_authors(publication_author_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    institution_id text REFERENCES institutions(institution_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    country_code text REFERENCES countries(country_code)
        ON UPDATE CASCADE ON DELETE SET NULL,
    raw_affiliation_string text
);

CREATE TABLE IF NOT EXISTS publication_countries (
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    country_code text NOT NULL REFERENCES countries(country_code)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    PRIMARY KEY (publication_id, country_code)
);

CREATE TABLE IF NOT EXISTS keywords (
    keyword_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    keyword_text text NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS publication_keywords (
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    keyword_id uuid NOT NULL REFERENCES keywords(keyword_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    PRIMARY KEY (publication_id, keyword_id)
);

CREATE TABLE IF NOT EXISTS research_topics (
    topic_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_topic_id uuid REFERENCES research_topics(topic_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    topic_name text NOT NULL,
    topic_level text NOT NULL,
    CONSTRAINT research_topics_level_valid
        CHECK (topic_level IN ('domain', 'field', 'subfield', 'topic', 'concept')),
    CONSTRAINT research_topics_unique_name_level
        UNIQUE (topic_name, topic_level)
);

CREATE TABLE IF NOT EXISTS publication_topics (
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    topic_id uuid NOT NULL REFERENCES research_topics(topic_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    is_primary boolean NOT NULL DEFAULT false,
    PRIMARY KEY (publication_id, topic_id)
);

CREATE TABLE IF NOT EXISTS funders (
    funder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    funder_name text NOT NULL,
    funder_doi text UNIQUE,
    funder_identifier text UNIQUE
);

CREATE TABLE IF NOT EXISTS publication_funders (
    publication_funder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    funder_id uuid NOT NULL REFERENCES funders(funder_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    award_number text,
    CONSTRAINT publication_funders_unique_award
        UNIQUE (publication_id, funder_id, award_number)
);

CREATE TABLE IF NOT EXISTS events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    event_name text NOT NULL,
    event_acronym text,
    event_location text,
    event_start_date date,
    event_end_date date,
    event_sponsor text,
    CONSTRAINT events_date_order_valid
        CHECK (
            event_start_date IS NULL
            OR event_end_date IS NULL
            OR event_end_date >= event_start_date
        )
);

CREATE TABLE IF NOT EXISTS publication_events (
    publication_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    event_id uuid NOT NULL REFERENCES events(event_id)
        ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT publication_events_unique_event
        UNIQUE (publication_id, event_id)
);

CREATE TABLE IF NOT EXISTS publication_references (
    reference_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    reference_index integer NOT NULL,
    reference_doi text,
    reference_title text,
    reference_author text,
    reference_year integer,
    raw_reference_json jsonb,
    CONSTRAINT publication_references_index_positive
        CHECK (reference_index > 0),
    CONSTRAINT publication_references_year_valid
        CHECK (reference_year IS NULL OR reference_year BETWEEN 1500 AND 2100),
    CONSTRAINT publication_references_unique_index
        UNIQUE (publication_id, reference_index)
);

CREATE TABLE IF NOT EXISTS publication_locations (
    location_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id uuid NOT NULL REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    landing_page_url text,
    pdf_url text,
    source_name text,
    source_type text,
    license text,
    version text
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name text NOT NULL,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    status text NOT NULL DEFAULT 'running',
    records_collected integer NOT NULL DEFAULT 0,
    records_inserted integer NOT NULL DEFAULT 0,
    records_failed integer NOT NULL DEFAULT 0,
    CONSTRAINT pipeline_runs_status_valid
        CHECK (status IN ('running', 'success', 'failed', 'partial')),
    CONSTRAINT pipeline_runs_counts_nonnegative
        CHECK (
            records_collected >= 0
            AND records_inserted >= 0
            AND records_failed >= 0
        )
);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_id uuid REFERENCES publications(publication_id)
        ON UPDATE CASCADE ON DELETE CASCADE,
    run_id uuid REFERENCES pipeline_runs(run_id)
        ON UPDATE CASCADE ON DELETE SET NULL,
    issue_type text NOT NULL,
    severity text NOT NULL,
    message text NOT NULL,
    CONSTRAINT data_quality_issues_severity_valid
        CHECK (severity IN ('info', 'warning', 'error', 'critical'))
);

CREATE INDEX IF NOT EXISTS idx_institutions_country_code
    ON institutions(country_code);
CREATE INDEX IF NOT EXISTS idx_institution_aliases_alias_name
    ON institution_aliases(alias_name);
CREATE INDEX IF NOT EXISTS idx_source_records_source_id
    ON source_records(source_id);
CREATE INDEX IF NOT EXISTS idx_source_records_source_institution_id
    ON source_records(source_institution_id);
CREATE INDEX IF NOT EXISTS idx_source_records_raw_payload_gin
    ON source_records USING gin(raw_payload);
CREATE INDEX IF NOT EXISTS idx_venues_venue_name
    ON venues(venue_name);
CREATE INDEX IF NOT EXISTS idx_publications_doi
    ON publications(doi);
CREATE INDEX IF NOT EXISTS idx_publications_openalex_id
    ON publications(openalex_id);
CREATE INDEX IF NOT EXISTS idx_publications_title
    ON publications(title);
CREATE INDEX IF NOT EXISTS idx_publications_publication_year
    ON publications(publication_year);
CREATE INDEX IF NOT EXISTS idx_publications_publication_type
    ON publications(publication_type);
CREATE INDEX IF NOT EXISTS idx_publications_venue_id
    ON publications(venue_id);
CREATE INDEX IF NOT EXISTS idx_publication_sources_publication_id
    ON publication_sources(publication_id);
CREATE INDEX IF NOT EXISTS idx_publication_sources_source_record_uuid
    ON publication_sources(source_record_uuid);
CREATE INDEX IF NOT EXISTS idx_authors_display_name
    ON authors(display_name);
CREATE INDEX IF NOT EXISTS idx_publication_authors_publication_id
    ON publication_authors(publication_id);
CREATE INDEX IF NOT EXISTS idx_publication_authors_author_id
    ON publication_authors(author_id);
CREATE INDEX IF NOT EXISTS idx_author_affiliations_publication_author_id
    ON author_affiliations(publication_author_id);
CREATE INDEX IF NOT EXISTS idx_author_affiliations_institution_id
    ON author_affiliations(institution_id);
CREATE INDEX IF NOT EXISTS idx_author_affiliations_country_code
    ON author_affiliations(country_code);
CREATE INDEX IF NOT EXISTS idx_publication_countries_country_code
    ON publication_countries(country_code);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword_text
    ON keywords(keyword_text);
CREATE INDEX IF NOT EXISTS idx_publication_keywords_keyword_id
    ON publication_keywords(keyword_id);
CREATE INDEX IF NOT EXISTS idx_research_topics_parent_topic_id
    ON research_topics(parent_topic_id);
CREATE INDEX IF NOT EXISTS idx_research_topics_topic_level
    ON research_topics(topic_level);
CREATE INDEX IF NOT EXISTS idx_publication_topics_topic_id
    ON publication_topics(topic_id);
CREATE INDEX IF NOT EXISTS idx_funders_funder_name
    ON funders(funder_name);
CREATE INDEX IF NOT EXISTS idx_publication_funders_publication_id
    ON publication_funders(publication_id);
CREATE INDEX IF NOT EXISTS idx_publication_funders_funder_id
    ON publication_funders(funder_id);
CREATE INDEX IF NOT EXISTS idx_events_event_name
    ON events(event_name);
CREATE INDEX IF NOT EXISTS idx_publication_events_publication_id
    ON publication_events(publication_id);
CREATE INDEX IF NOT EXISTS idx_publication_events_event_id
    ON publication_events(event_id);
CREATE INDEX IF NOT EXISTS idx_publication_references_publication_id
    ON publication_references(publication_id);
CREATE INDEX IF NOT EXISTS idx_publication_references_reference_doi
    ON publication_references(reference_doi);
CREATE INDEX IF NOT EXISTS idx_publication_locations_publication_id
    ON publication_locations(publication_id);
CREATE INDEX IF NOT EXISTS idx_pipeline_runs_source_name
    ON pipeline_runs(source_name);
CREATE INDEX IF NOT EXISTS idx_data_quality_issues_publication_id
    ON data_quality_issues(publication_id);
CREATE INDEX IF NOT EXISTS idx_data_quality_issues_run_id
    ON data_quality_issues(run_id);
