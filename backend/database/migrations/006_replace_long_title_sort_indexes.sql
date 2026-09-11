DROP INDEX IF EXISTS idx_final_publications_year_desc_title;
DROP INDEX IF EXISTS idx_final_publications_year_asc_title;
DROP INDEX IF EXISTS idx_final_publications_title_asc_year_desc;

CREATE INDEX IF NOT EXISTS idx_final_publications_year_desc_title_prefix
    ON final_publications(publication_year DESC NULLS LAST, left(coalesce(title, ''), 512));

CREATE INDEX IF NOT EXISTS idx_final_publications_year_asc_title_prefix
    ON final_publications(publication_year ASC NULLS LAST, left(coalesce(title, ''), 512));

CREATE INDEX IF NOT EXISTS idx_final_publications_title_prefix_year_desc
    ON final_publications(left(coalesce(title, ''), 512), publication_year DESC NULLS LAST);
