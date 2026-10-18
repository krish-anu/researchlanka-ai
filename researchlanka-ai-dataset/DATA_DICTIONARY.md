# Data Dictionary

All fields are stored as strings in the CSV release.

| Column | Description |
| --- | --- |
| `source_dataset` | Source collection(s) that contributed the merged publication record. |
| `source_institution_id` | Source repository or institution identifier where available. |
| `source_record_id` | Identifier assigned by the source system or collection pipeline. |
| `source_datestamp` | Source harvest datestamp when available. |
| `openalex_id` | OpenAlex work identifier. |
| `doi` | Digital Object Identifier, when available. |
| `url` | Publication landing page URL. |
| `pdf_url` | Direct PDF URL when available. |
| `title` | Publication title. |
| `abstract` | Publication abstract or description. |
| `keywords` | Source or normalized keywords. |
| `publication_date` | Publication date, normally ISO-like `YYYY-MM-DD` when available. |
| `type` | Publication type, such as article, proceedings article, book chapter, or preprint. |
| `authors` | Publication author names. |
| `author_count` | Number of authors where available. |
| `author_affiliations` | Raw or normalized affiliation strings. |
| `author_orcids` | ORCID identifiers when available. |
| `sri_lankan_authors` | Authors or author evidence associated with Sri Lanka. |
| `contributors` | Non-author contributors when available. |
| `institutions` | Institution names associated with the publication. |
| `sri_lankan_institutions` | Sri Lankan institutions associated with the publication. |
| `countries` | Countries detected from source metadata. |
| `ownership_decision` | Sri Lanka ownership or inclusion decision. |
| `ownership_class` | Normalized ownership class used by the pipeline. |
| `ownership_confidence` | Confidence score for Sri Lanka ownership decision. |
| `ownership_reason` | Reason for ownership decision. |
| `ownership_evidence` | Evidence used for Sri Lanka relevance decision. |
| `lead_country` | Lead or primary country inferred from metadata when available. |
| `corresponding_author_countries` | Corresponding author countries when available. |
| `has_sri_lankan_participant` | Whether a Sri Lankan participant was detected. |
| `has_foreign_participant` | Whether a foreign participant was detected. |
| `needs_manual_review` | Whether the Sri Lanka ownership decision was marked for manual review. |
| `ownership_policy_version` | Version of the ownership policy used by the pipeline. |
| `publisher` | Publisher name. |
| `journal` | Journal, conference, or source title. |
| `source_type` | Source venue type where available. |
| `issn` | ISSN values. |
| `issn_l` | Linking ISSN. |
| `volume` | Volume information. |
| `issue` | Issue information. |
| `first_page` | First page. |
| `last_page` | Last page. |
| `article_number` | Article number or electronic locator. |
| `language` | Publication language. |
| `license` | License label from source metadata. |
| `license_url` | License URL from source metadata. |
| `oa_status` | Open-access status. |
| `is_oa` | Whether the work is open access according to source metadata. |
| `reference_count` | Number of references where available. |
| `concepts` | OpenAlex concepts or source concepts. |
| `topics` | Topic labels. |
| `primary_topic` | Primary topic label. |
| `primary_field` | Primary field label. |
| `primary_subfield` | Primary subfield label. |
| `primary_domain` | Primary domain label. |
| `funder_name` | Funder name. |
| `funder_doi` | Funder DOI. |
| `funder_identifier` | Funder identifier. |
| `funder_award` | Funder award identifier or text. |
| `source_set_specs` | OAI-PMH set specs or equivalent source grouping metadata. |
| `reference_count_difference_oa_minus_crossref` | Difference between OpenAlex and Crossref reference counts, where compared. |
| `reference_count_divergence_flag` | Flag indicating reference-count divergence. |
| `title_search_text` | Normalized lowercase title used for search. |
| `abstract_search_text` | Normalized lowercase abstract used for search. |
| `abstract_missing_flag` | Whether a usable abstract is absent. |
| `keywords_search_text` | Normalized lowercase keywords used for search. |
| `funder_name_missing_flag` | Whether funder name is absent. |
| `funder_doi_missing_flag` | Whether funder DOI is absent. |
| `funder_identifier_missing_flag` | Whether funder identifier is absent. |
| `funder_award_missing_flag` | Whether funder award is absent. |
| `license_missing_flag` | Whether license metadata is absent. |
| `license_url_missing_flag` | Whether the license URL is absent. |
| `pdf_url_missing_flag` | Whether a PDF URL is absent. |
| `author_orcids_missing_flag` | Whether author ORCID metadata is absent. |
| `article_number_missing_flag` | Whether an article number is absent. |
| `authors_clean` | Normalized author representation used by downstream processing. |
| `author_disambiguation_available_flag` | Whether author-disambiguation evidence is available. |
| `ai_classification_label` | Final AI relevance label included in this release. All release rows should be `AI`. |
| `ai_classification_confidence` | Confidence-like value recorded by the classifier. Finished human-review decisions use `not_applicable`; scores from different model sources are not directly comparable. |
| `ai_classification_model` | Portable identifier for the model or review process used. |
| `ai_classification_reason` | Model or threshold reason when applicable. |
| `final_resolution_source` | Process that supplied the final AI decision. |
| `a2_pending_decision` | Historical A2 decision retained for audit provenance. |
| `a2_pending_binary_prediction` | Historical A2 binary prediction retained for audit provenance. |
| `a2_pending_ai_score` | Historical A2 AI score retained for audit provenance. |
| `a2_pending_model_path` | Historical A2 model reference retained for audit provenance. |
