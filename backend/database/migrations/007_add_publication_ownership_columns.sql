ALTER TABLE final_publications
    ADD COLUMN IF NOT EXISTS ownership_decision text,
    ADD COLUMN IF NOT EXISTS ownership_class text,
    ADD COLUMN IF NOT EXISTS ownership_confidence text,
    ADD COLUMN IF NOT EXISTS ownership_reason text,
    ADD COLUMN IF NOT EXISTS ownership_evidence text,
    ADD COLUMN IF NOT EXISTS lead_country text,
    ADD COLUMN IF NOT EXISTS corresponding_author_countries text,
    ADD COLUMN IF NOT EXISTS has_sri_lankan_participant text,
    ADD COLUMN IF NOT EXISTS has_foreign_participant text,
    ADD COLUMN IF NOT EXISTS needs_manual_review text,
    ADD COLUMN IF NOT EXISTS ownership_policy_version text;
