CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_final_publications_year_desc_title
    ON final_publications(publication_year DESC NULLS LAST, left(coalesce(title, ''), 512));

CREATE INDEX IF NOT EXISTS idx_final_publications_year_asc_title
    ON final_publications(publication_year ASC NULLS LAST, left(coalesce(title, ''), 512));

CREATE INDEX IF NOT EXISTS idx_final_publications_citations_desc_year_desc
    ON final_publications(citation_count DESC NULLS LAST, publication_year DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_final_publications_title_asc_year_desc
    ON final_publications(left(coalesce(title, ''), 512), publication_year DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_final_publications_type_year
    ON final_publications(type, publication_year DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_final_publications_primary_field_year
    ON final_publications(primary_field, publication_year DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_final_publications_primary_subfield_year
    ON final_publications(primary_subfield, publication_year DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_final_publications_journal_year
    ON final_publications(journal, publication_year DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_final_publications_has_doi_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE doi IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_final_publications_missing_doi_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE doi IS NULL;

CREATE INDEX IF NOT EXISTS idx_final_publications_has_abstract_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE abstract IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_final_publications_missing_abstract_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE abstract IS NULL;

CREATE INDEX IF NOT EXISTS idx_final_publications_is_oa_true_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE is_oa IS TRUE;

CREATE INDEX IF NOT EXISTS idx_final_publications_is_oa_false_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE is_oa IS FALSE;

CREATE INDEX IF NOT EXISTS idx_final_publications_citation_divergence_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE citation_count_divergence_flag IS TRUE;

CREATE INDEX IF NOT EXISTS idx_final_publications_reference_divergence_year
    ON final_publications(publication_year DESC NULLS LAST)
    WHERE reference_count_divergence_flag IS TRUE;

CREATE INDEX IF NOT EXISTS idx_final_publications_authors_trgm
    ON final_publications USING gin(authors gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_sri_lankan_authors_trgm
    ON final_publications USING gin(sri_lankan_authors gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_institutions_trgm
    ON final_publications USING gin(institutions gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_sri_lankan_institutions_trgm
    ON final_publications USING gin(sri_lankan_institutions gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_countries_trgm
    ON final_publications USING gin(countries gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_topics_trgm
    ON final_publications USING gin(topics gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_concepts_trgm
    ON final_publications USING gin(concepts gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_primary_topic_trgm
    ON final_publications USING gin(primary_topic gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publications_source_dataset_trgm
    ON final_publications USING gin(source_dataset gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_final_publication_references_publication_key_index
    ON final_publication_references(publication_key, reference_index);
