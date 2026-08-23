ALTER TABLE final_publications
    ADD COLUMN IF NOT EXISTS author_ids text,
    ADD COLUMN IF NOT EXISTS author_disambiguation_level text;
