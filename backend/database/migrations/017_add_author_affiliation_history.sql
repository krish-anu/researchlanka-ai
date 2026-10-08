-- Where an author worked, and when.
--
-- This is the author's own account of their career, shown on their profile
-- and used to pre-fill their institution on a publication they add. It never
-- rewrites an existing publication: institution counts come from each
-- publication's own affiliations, so work done before a move keeps counting
-- for the institution it was done at.

CREATE TABLE IF NOT EXISTS author_profile_affiliations (
    affiliation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    profile_id uuid NOT NULL REFERENCES author_profiles(profile_id)
        ON DELETE CASCADE,
    institution text NOT NULL,
    department text NOT NULL DEFAULT '',
    position_title text NOT NULL DEFAULT '',
    start_year integer,
    -- NULL means the author is still there.
    end_year integer,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT author_profile_affiliations_years_valid CHECK (
        (start_year IS NULL OR start_year BETWEEN 1950 AND 2100)
        AND (end_year IS NULL OR end_year BETWEEN 1950 AND 2100)
        AND (start_year IS NULL OR end_year IS NULL OR start_year <= end_year)
    )
);

CREATE INDEX IF NOT EXISTS idx_author_profile_affiliations_profile
    ON author_profile_affiliations(profile_id, start_year);

-- The claimant's own institution on a publication, when it is known exactly:
-- set for publications they added, where each author named an institution.
-- For harvested records it stays NULL and is inferred from the history above.
ALTER TABLE author_publication_claims
    ADD COLUMN IF NOT EXISTS institution text;

-- Claims on the same listed name are approved and reviewed together when an
-- author merges a name spelling into their profile.
CREATE INDEX IF NOT EXISTS idx_author_claims_listed_name
    ON author_publication_claims(lower(name_as_listed), status);
