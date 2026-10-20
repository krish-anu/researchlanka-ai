# Public Data Dictionary

The public CSV contains the following 35 string-valued columns. Additional
processing, review, diagnostic, and search-helper fields remain in the private
86-column application master.

| Column | Description |
| --- | --- |
| `openalex_id` | OpenAlex work identifier. |
| `doi` | Digital Object Identifier, when available. |
| `url` | Publication landing-page URL. |
| `pdf_url` | Direct PDF URL when available. |
| `source_dataset` | Source collection(s) contributing the merged record. |
| `source_record_id` | Identifier assigned by the source system or pipeline. |
| `title` | Publication title. |
| `abstract` | Publication abstract or description when available. |
| `keywords` | Source or normalized keywords. |
| `publication_date` | Publication date, normally ISO-like when available. |
| `type` | Publication type, such as article, proceedings paper, chapter, or preprint. |
| `language` | Publication language code when available. |
| `authors` | Publication author names. |
| `author_orcids` | Author ORCID identifiers when available. |
| `author_affiliations` | Raw or normalized author affiliations. |
| `institutions` | Institutions associated with the publication. |
| `sri_lankan_institutions` | Sri Lankan institutions associated with the publication. |
| `countries` | Countries detected from source metadata. |
| `ownership_class` | Normalized Sri Lanka ownership class used for inclusion. |
| `publisher` | Publisher name. |
| `journal` | Journal, conference, or source title. |
| `issn` | ISSN values when available. |
| `volume` | Publication volume. |
| `issue` | Publication issue. |
| `first_page` | First page. |
| `last_page` | Last page. |
| `article_number` | Article number or electronic locator. |
| `topics` | Topic labels. |
| `primary_topic` | Primary topic label. |
| `primary_field` | Primary research field. |
| `primary_subfield` | Primary research subfield. |
| `license` | Source-provided licence label when available. |
| `license_url` | Source-provided licence URL when available. |
| `oa_status` | Open-access status reported by the source. |
| `ai_classification_label` | Final AI relevance label; all released records are `AI`. |

Empty values mean that the corresponding metadata was not obtained. Array-like
values are represented as semicolon-delimited strings.
