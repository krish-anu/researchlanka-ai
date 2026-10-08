-- Author profiles, publication claims, author contributions and corrections.
--
-- Accounts live in the frontend account store; `author_profiles.user_id` is
-- that account id. Everything an author changes is kept out of the pipeline
-- columns of final_publications:
--   * approved edits live in publication_corrections and are merged into the
--     public view, so a pipeline reload cannot overwrite them;
--   * approved new publications are inserted with
--     source_dataset = 'author_submission', which retire-stale skips.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS author_profiles (
    profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id text NOT NULL,
    user_email text NOT NULL,
    slug text NOT NULL,
    display_name text NOT NULL,
    name_variants text[] NOT NULL DEFAULT '{}',
    orcid text,
    institution text NOT NULL,
    department text NOT NULL DEFAULT '',
    position_title text NOT NULL DEFAULT '',
    bio text NOT NULL DEFAULT '',
    website_url text,
    google_scholar_url text,
    researchgate_url text,
    linkedin_url text,
    application_note text NOT NULL DEFAULT '',
    status text NOT NULL DEFAULT 'pending',
    decision_reason text NOT NULL DEFAULT '',
    decided_by_id text,
    decided_by_email text,
    decided_by_name text,
    decided_at timestamptz,
    record_version integer NOT NULL DEFAULT 1,
    submitted_at timestamptz NOT NULL DEFAULT now(),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT author_profiles_user_unique UNIQUE (user_id),
    CONSTRAINT author_profiles_slug_unique UNIQUE (slug),
    CONSTRAINT author_profiles_status_valid CHECK (
        status IN ('pending', 'changes_requested', 'approved', 'rejected')
    ),
    CONSTRAINT author_profiles_orcid_format CHECK (
        orcid IS NULL OR orcid ~ '^[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]$'
    )
);

-- One approved profile per ORCID; pending duplicates are left for the admin.
CREATE UNIQUE INDEX IF NOT EXISTS idx_author_profiles_orcid_approved
    ON author_profiles(orcid)
    WHERE orcid IS NOT NULL AND status = 'approved';
CREATE INDEX IF NOT EXISTS idx_author_profiles_status_submitted
    ON author_profiles(status, submitted_at);

CREATE TABLE IF NOT EXISTS author_publication_claims (
    claim_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES author_profiles(profile_id)
        ON DELETE CASCADE,
    -- ON UPDATE CASCADE keeps the claim attached when the loader
    -- canonicalises a record to a better identifier.
    publication_key text NOT NULL REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE CASCADE,
    name_as_listed text NOT NULL,
    author_position integer,
    status text NOT NULL DEFAULT 'pending',
    decision_reason text NOT NULL DEFAULT '',
    decided_by_id text,
    decided_by_email text,
    decided_by_name text,
    decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT author_publication_claims_status_valid CHECK (
        status IN ('pending', 'approved', 'rejected')
    ),
    CONSTRAINT author_publication_claims_position_valid CHECK (
        author_position IS NULL OR author_position >= 1
    ),
    CONSTRAINT author_publication_claims_profile_publication_unique
        UNIQUE (profile_id, publication_key)
);

-- Two people cannot both hold an approved claim on the same listed author.
CREATE UNIQUE INDEX IF NOT EXISTS idx_author_claims_listed_author_approved
    ON author_publication_claims(publication_key, lower(name_as_listed))
    WHERE status = 'approved';
CREATE INDEX IF NOT EXISTS idx_author_claims_status_created
    ON author_publication_claims(status, created_at);
CREATE INDEX IF NOT EXISTS idx_author_claims_publication
    ON author_publication_claims(publication_key);

CREATE TABLE IF NOT EXISTS author_contributions (
    contribution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES author_profiles(profile_id)
        ON DELETE CASCADE,
    contribution_type text NOT NULL,
    -- The edited record, or the record created when a new publication is approved.
    publication_key text REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE SET NULL,
    proposed jsonb NOT NULL,
    -- Public values of the edited fields when the edit was proposed.
    base_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
    author_note text NOT NULL DEFAULT '',
    lookup_source text NOT NULL DEFAULT 'manual',
    lookup_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
    classifier jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'pending',
    decision_reason text NOT NULL DEFAULT '',
    decided_by_id text,
    decided_by_email text,
    decided_by_name text,
    decided_at timestamptz,
    record_version integer NOT NULL DEFAULT 1,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT author_contributions_type_valid CHECK (
        contribution_type IN ('publication_edit', 'new_publication')
    ),
    CONSTRAINT author_contributions_status_valid CHECK (
        status IN ('pending', 'approved', 'rejected', 'withdrawn')
    ),
    CONSTRAINT author_contributions_lookup_source_valid CHECK (
        lookup_source IN ('manual', 'openalex', 'crossref')
    )
);

CREATE INDEX IF NOT EXISTS idx_author_contributions_status_created
    ON author_contributions(status, created_at);
CREATE INDEX IF NOT EXISTS idx_author_contributions_profile_status
    ON author_contributions(profile_id, status);
-- One open edit per author per publication, so reviews never race each other.
CREATE UNIQUE INDEX IF NOT EXISTS idx_author_contributions_pending_edit
    ON author_contributions(profile_id, publication_key)
    WHERE status = 'pending' AND contribution_type = 'publication_edit';

CREATE TABLE IF NOT EXISTS author_profile_events (
    event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES author_profiles(profile_id)
        ON DELETE CASCADE,
    subject_type text NOT NULL,
    subject_id uuid NOT NULL,
    event_type text NOT NULL,
    actor_id text,
    actor_email text,
    actor_name text,
    from_status text,
    to_status text,
    notes text NOT NULL DEFAULT '',
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT author_profile_events_subject_valid CHECK (
        subject_type IN ('profile', 'claim', 'contribution')
    )
);

CREATE INDEX IF NOT EXISTS idx_author_profile_events_profile_created
    ON author_profile_events(profile_id, created_at);
CREATE INDEX IF NOT EXISTS idx_author_profile_events_subject_created
    ON author_profile_events(subject_id, created_at);

-- Approved author corrections, one row per publication. A NULL column means
-- "no correction": the pipeline value shows through.
CREATE TABLE IF NOT EXISTS publication_corrections (
    publication_key text PRIMARY KEY REFERENCES final_publications(publication_key)
        ON UPDATE CASCADE ON DELETE CASCADE,
    title text,
    abstract text,
    keywords text,
    publication_year integer,
    type text,
    journal text,
    publisher text,
    volume text,
    issue text,
    first_page text,
    last_page text,
    language text,
    url text,
    pdf_url text,
    last_contribution_id uuid REFERENCES author_contributions(contribution_id)
        ON DELETE SET NULL,
    corrected_by_id text,
    corrected_by_email text,
    corrected_by_name text,
    corrected_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT publication_corrections_year_valid CHECK (
        publication_year IS NULL OR publication_year BETWEEN 1500 AND 2100
    )
);

-- Rebuild the public views from the live final_publications column list.
--
-- Later migrations that add final_publications columns should call this
-- function instead of writing the view by hand, or author corrections stop
-- reaching the public API. The corrected column list must match
-- EDITABLE_PUBLICATION_FIELDS in src/api/services/author_profiles.py.
CREATE OR REPLACE FUNCTION refresh_public_publication_views() RETURNS void
LANGUAGE plpgsql
AS $function$
DECLARE
    corrected_columns text[] := ARRAY[
        'title', 'abstract', 'keywords', 'publication_year', 'type',
        'journal', 'publisher', 'volume', 'issue', 'first_page',
        'last_page', 'language', 'url', 'pdf_url'
    ];
    select_list text;
BEGIN
    SELECT string_agg(
        CASE
            WHEN columns.column_name = ANY(corrected_columns)
                THEN format('COALESCE(c.%1$I, p.%1$I) AS %1$I', columns.column_name)
            ELSE format('p.%I', columns.column_name)
        END,
        ', ' ORDER BY columns.ordinal_position
    )
    INTO select_list
    FROM information_schema.columns AS columns
    WHERE columns.table_schema = current_schema()
      AND columns.table_name = 'final_publications';

    IF select_list IS NULL THEN
        RAISE EXCEPTION 'final_publications does not exist in schema %', current_schema();
    END IF;

    -- Qualified, so a view of the same name further down search_path is never touched.
    EXECUTE format('DROP VIEW IF EXISTS %I.accepted_ai_publications', current_schema());
    EXECUTE format('DROP VIEW IF EXISTS %I.public_eligible_publications', current_schema());

    EXECUTE format(
        $view$
        CREATE VIEW public_eligible_publications AS
        SELECT
            %s,
            r.review_status,
            COALESCE(r.decided_by_email, r.decided_by_name, r.assigned_reviewer_email) AS reviewed_by,
            r.decision_timestamp AS reviewed_at,
            (c.publication_key IS NOT NULL) AS has_author_corrections
        FROM final_publications p
        JOIN ai_review_records r ON r.publication_key = p.publication_key
        LEFT JOIN publication_corrections c ON c.publication_key = p.publication_key
        WHERE p.retired_at IS NULL
          AND r.review_status IN ('auto_accepted', 'human_accepted')
          AND upper(coalesce(p.ownership_decision, '')) = 'INCLUDE'
          AND upper(coalesce(p.ownership_confidence, '')) IN ('HIGH', 'MEDIUM')
          AND lower(coalesce(p.needs_manual_review, 'false')) NOT IN ('true', '1', 'yes')
        $view$,
        select_list
    );

    CREATE VIEW accepted_ai_publications AS
    SELECT * FROM public_eligible_publications;
END;
$function$;

SELECT refresh_public_publication_views();
