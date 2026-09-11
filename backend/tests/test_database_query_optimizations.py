from pathlib import Path


MIGRATION_PATH = (
    Path(__file__).resolve().parents[1]
    / "database"
    / "migrations"
    / "005_optimize_final_publication_api_queries.sql"
)


def migration_sql() -> str:
    return MIGRATION_PATH.read_text(encoding="utf-8")


def test_api_query_optimization_migration_enables_trigram_indexes():
    sql = migration_sql()

    assert "CREATE EXTENSION IF NOT EXISTS pg_trgm;" in sql
    for column in [
        "authors",
        "sri_lankan_authors",
        "institutions",
        "sri_lankan_institutions",
        "countries",
        "topics",
        "concepts",
        "primary_topic",
        "source_dataset",
    ]:
        assert f"ON final_publications USING gin({column} gin_trgm_ops)" in sql


def test_api_query_optimization_migration_adds_sort_and_filter_indexes():
    sql = migration_sql()

    assert "ON final_publications(publication_year DESC NULLS LAST, left(coalesce(title, ''), 512))" in sql
    assert "ON final_publications(publication_year ASC NULLS LAST, left(coalesce(title, ''), 512))" in sql
    assert "ON final_publications(citation_count DESC NULLS LAST, publication_year DESC NULLS LAST)" in sql
    assert "ON final_publications(left(coalesce(title, ''), 512), publication_year DESC NULLS LAST)" in sql
    assert "ON final_publications(type, publication_year DESC NULLS LAST)" in sql
    assert "ON final_publications(primary_field, publication_year DESC NULLS LAST)" in sql
    assert "ON final_publications(primary_subfield, publication_year DESC NULLS LAST)" in sql
    assert "ON final_publications(journal, publication_year DESC NULLS LAST)" in sql


def test_api_query_optimization_migration_adds_partial_and_reference_indexes():
    sql = migration_sql()

    for predicate in [
        "WHERE doi IS NOT NULL",
        "WHERE doi IS NULL",
        "WHERE abstract IS NOT NULL",
        "WHERE abstract IS NULL",
        "WHERE is_oa IS TRUE",
        "WHERE is_oa IS FALSE",
        "WHERE citation_count_divergence_flag IS TRUE",
        "WHERE reference_count_divergence_flag IS TRUE",
    ]:
        assert predicate in sql
    assert "ON final_publication_references(publication_key, reference_index)" in sql
