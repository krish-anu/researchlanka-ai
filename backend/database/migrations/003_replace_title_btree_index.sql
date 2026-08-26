DROP INDEX IF EXISTS idx_final_publications_title;

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
