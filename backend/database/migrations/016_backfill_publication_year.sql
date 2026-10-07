WITH candidate_years AS (
    SELECT
        publication_key,
        COALESCE(
            EXTRACT(YEAR FROM publication_date)::integer,
            substring(
                raw_record ->> 'publication_year'
                FROM '^[[:space:]]*([0-9]{4})'
            )::integer,
            substring(
                raw_record ->> 'publication_date'
                FROM '^[[:space:]]*([0-9]{4})'
            )::integer
        ) AS publication_year
    FROM final_publications
    WHERE publication_year IS NULL
)
UPDATE final_publications AS publications
SET publication_year = candidates.publication_year,
    updated_at = now()
FROM candidate_years AS candidates
WHERE publications.publication_key = candidates.publication_key
  AND candidates.publication_year BETWEEN 1500 AND 2100;
