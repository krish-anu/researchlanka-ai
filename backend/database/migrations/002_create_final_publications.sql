CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS final_publications (
    publication_key text PRIMARY KEY,
    source_dataset text,
    source_institution_id text,
    source_record_id text,
    source_datestamp timestamptz,
    openalex_id text,
    doi text,
    url text,
    pdf_url text,
    title text,
    abstract text,
    keywords text,
    publication_year integer,
    publication_date date,
    type text,
    authors text,
    author_ids text,
    author_count integer,
    author_affiliations text,
    author_orcids text,
    author_disambiguation_level text,
    sri_lankan_authors text,
    contributors text,
    institutions text,
    sri_lankan_institutions text,
    countries text,
    publisher text,
    journal text,
    source_type text,
    issn text,
    issn_l text,
    volume text,
    issue text,
    first_page text,
    last_page text,
    article_number text,
    language text,
    license text,
    license_url text,
    oa_status text,
    is_oa boolean,
    citation_count integer,
    reference_count integer,
    concepts text,
    topics text,
    primary_topic text,
    primary_field text,
    primary_subfield text,
    primary_domain text,
    funder_name text,
    funder_doi text,
    funder_identifier text,
    funder_award text,
    source_set_specs text,
    raw_identifiers text,
    citation_count_difference_oa_minus_crossref integer,
    citation_count_divergence_flag boolean,
    reference_count_difference_oa_minus_crossref integer,
    reference_count_divergence_flag boolean,
    raw_record jsonb NOT NULL DEFAULT '{}'::jsonb,
    loaded_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT final_publications_publication_year_valid
        CHECK (publication_year IS NULL OR publication_year BETWEEN 1500 AND 2100),
    CONSTRAINT final_publications_author_count_nonnegative
        CHECK (author_count IS NULL OR author_count >= 0),
    CONSTRAINT final_publications_citation_count_nonnegative
        CHECK (citation_count IS NULL OR citation_count >= 0),
    CONSTRAINT final_publications_reference_count_nonnegative
        CHECK (reference_count IS NULL OR reference_count >= 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_final_publications_doi_unique
    ON final_publications(doi)
    WHERE doi IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_final_publications_openalex_id_unique
    ON final_publications(openalex_id)
    WHERE openalex_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_final_publications_source_record
    ON final_publications(source_dataset, source_record_id);
CREATE INDEX IF NOT EXISTS idx_final_publications_publication_year
    ON final_publications(publication_year);
CREATE INDEX IF NOT EXISTS idx_final_publications_search_gin
    ON final_publications USING gin(
        to_tsvector(
            'english',
            coalesce(title, '') || ' ' ||
            coalesce(abstract, '') || ' ' ||
            coalesce(authors, '') || ' ' ||
            coalesce(keywords, '') || ' ' ||
            coalesce(journal, '') || ' ' ||
            coalesce(publisher, '') || ' ' ||
            coalesce(doi, '') || ' ' ||
            coalesce(openalex_id, '')
        )
    );
CREATE INDEX IF NOT EXISTS idx_final_publications_primary_field
    ON final_publications(primary_field);
CREATE INDEX IF NOT EXISTS idx_final_publications_primary_subfield
    ON final_publications(primary_subfield);
CREATE INDEX IF NOT EXISTS idx_final_publications_journal
    ON final_publications(journal);
CREATE INDEX IF NOT EXISTS idx_final_publications_raw_record_gin
    ON final_publications USING gin(raw_record);

CREATE TABLE IF NOT EXISTS final_publication_references (
    reference_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    publication_key text NOT NULL REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE CASCADE,
    publication_row_number integer,
    source_dataset text,
    source_record_id text,
    doi text,
    reference_index integer NOT NULL,
    reference_doi text,
    reference_title text,
    reference_author text,
    reference_year integer,
    raw_reference_json jsonb,
    CONSTRAINT final_publication_references_index_positive
        CHECK (reference_index > 0),
    CONSTRAINT final_publication_references_year_valid
        CHECK (reference_year IS NULL OR reference_year BETWEEN 1500 AND 2100),
    CONSTRAINT final_publication_references_unique_index
        UNIQUE (publication_key, reference_index)
);

CREATE INDEX IF NOT EXISTS idx_final_publication_references_publication_key
    ON final_publication_references(publication_key);
CREATE INDEX IF NOT EXISTS idx_final_publication_references_reference_doi
    ON final_publication_references(reference_doi);

CREATE TABLE IF NOT EXISTS final_publication_count_audit (
    publication_key text PRIMARY KEY REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE CASCADE,
    publication_row_number integer,
    source_dataset text,
    source_record_id text,
    doi text,
    title text,
    citation_count integer,
    is_referenced_by_count integer,
    reference_count integer,
    referenced_works_count integer,
    citation_count_difference_oa_minus_crossref integer,
    citation_count_divergence_flag boolean,
    reference_count_difference_oa_minus_crossref integer,
    reference_count_divergence_flag boolean
);

CREATE INDEX IF NOT EXISTS idx_final_publication_count_audit_doi
    ON final_publication_count_audit(doi);
