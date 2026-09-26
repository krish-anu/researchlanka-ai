CREATE OR REPLACE VIEW public_eligible_publications AS
SELECT p.*
FROM final_publications p
JOIN ai_review_records r ON r.publication_key = p.publication_key
WHERE r.review_status IN ('auto_accepted', 'human_accepted')
  AND upper(coalesce(p.ownership_decision, '')) = 'INCLUDE'
  AND upper(coalesce(p.ownership_confidence, '')) IN ('HIGH', 'MEDIUM')
  AND lower(coalesce(p.needs_manual_review, 'false')) NOT IN ('true', '1', 'yes');

CREATE OR REPLACE VIEW accepted_ai_publications AS
SELECT *
FROM public_eligible_publications;
