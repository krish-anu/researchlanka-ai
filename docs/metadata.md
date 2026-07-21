# Publication Metadata Schema

Canonical schema for normalizing research publication metadata from multiple sources (OpenAlex, Crossref, repositories).

---

## 1. Core Identification

| Canonical Field    | OpenAlex Field | Crossref Field | Description               |
| ------------------ | -------------- | -------------- | ------------------------- |
| `record_id`        | -              | -              | Internal UUID identifier  |
| `source_record_id` | `openalex_id`  | URL/DOI        | Source-specific record ID |
| `doi`              | `doi`          | `DOI`          | Digital Object Identifier |
| `title`            | `title`        | `title`        | Publication title         |
| `subtitle`         | -              | `subtitle`     | Publication subtitle      |
| `type`             | `type`         | `type`         | Publication type          |
| `subtype`          | -              | `subtype`      | Publication subtype       |

---

## 2. Publication Metadata

| Canonical Field    | OpenAlex Field     | Crossref Field         | Description                    |
| ------------------ | ------------------ | ---------------------- | ------------------------------ |
| `publication_year` | `publication_year` | `published.date-parts` | Year of publication            |
| `publication_date` | `publication_date` | `published.date-parts` | Full publication date          |
| `created_date`     | `created_date`     | `created.date-parts`   | Record creation date           |
| `updated_date`     | `updated_date`     | -                      | Last record update             |
| `language`         | `language`         | `language`             | Publication language (ISO 639) |

**Note:** Dates typically stored as `[YYYY, MM, DD]` arrays.

---

## 3. Venue / Journal Metadata

| Canonical Field      | OpenAlex Field   | Crossref Field       | Description                            |
| -------------------- | ---------------- | -------------------- | -------------------------------------- |
| `venue_name`         | `source_name`    | `container-title`    | Journal/venue name                     |
| `venue_type`         | `source_type`    | -                    | Venue type (journal, conference, etc.) |
| `publisher`          | `publisher`      | `publisher`          | Publisher name                         |
| `publisher_location` | -                | `publisher-location` | Publisher location                     |
| `issn`               | -                | `ISSN`               | International Standard Serial Number   |
| `issn_l`             | `journal_issn_l` | -                    | ISSN (linking)                         |
| `volume`             | `volume`         | `volume`             | Journal volume number                  |
| `issue`              | `issue`          | `issue`              | Journal issue number                   |
| `first_page`         | `first_page`     | `first_page`         | Article first page                     |
| `last_page`          | `last_page`      | `last_page`          | Article last page                      |
| `article_number`     | -                | `article-number`     | Article number (for online journals)   |

**Primary Sources:** Mostly OpenAlex and Crossref

---

## 4. Authors & Editors

| Canonical Field | OpenAlex Field | Crossref Field | Description              |
| --------------- | -------------- | -------------- | ------------------------ |
| `author_count`  | `author_count` | Derived        | Total number of authors  |
| `authors`       | `authors`      | `author`       | Author list with details |
| `editors`       | -              | `editor`       | Editor list              |

**Structure:** `{name, orcid, affiliation, email, sequence}`

---

## 5. Affiliations & Geography

| Canonical Field           | OpenAlex Field | Crossref Field | Description                  |
| ------------------------- | -------------- | -------------- | ---------------------------- |
| `institutions`            | `institutions` | -              | Affiliated institutions      |
| `institution_count`       | -              | -              | Total number of institutions |
| `countries`               | `countries`    | -              | Author countries             |
| `country_count`           | -              | -              | Number of countries          |
| `sri_lankan_authors`      | -              | -              | Authors with LK affiliation  |
| `sri_lankan_institutions` | -              | -              | Institutions from Sri Lanka  |

**Primary Source:** Mostly OpenAlex and repository metadata

---

## 6. Impact Metrics

| Canonical Field   | OpenAlex Field           | Crossref Field           | Description                    |
| ----------------- | ------------------------ | ------------------------ | ------------------------------ |
| `citation_count`  | `cited_by_count`         | `is-referenced-by-count` | Number of citations            |
| `reference_count` | `referenced_works_count` | `reference-count`        | Number of references           |
| `fwci`            | `fwci`                   | -                        | Field-Weighted Citation Impact |

**Note:** OpenAlex updates citation counts regularly; Crossref may have historical data.

---

## 7. Open Access

| Canonical Field    | OpenAlex Field     | Crossref Field | Description                             |
| ------------------ | ------------------ | -------------- | --------------------------------------- |
| `is_open_access`   | `is_oa`            | -              | Open access status                      |
| `oa_status`        | `oa_status`        | -              | OA status (gold, green, hybrid, bronze) |
| `landing_page_url` | `landing_page_url` | `URL`          | Publisher landing page                  |
| `pdf_url`          | -                  | -              | Direct PDF URL (if available)           |

**Primary Source:** Mostly OpenAlex

---

## 8. Research Classification

| Canonical Field    | Description                   | Source                     |
| ------------------ | ----------------------------- | -------------------------- |
| `primary_topic`    | Main research topic           | OpenAlex ML classification |
| `primary_subfield` | Subfield classification       | OpenAlex ML classification |
| `primary_field`    | Broad field classification    | OpenAlex ML classification |
| `primary_domain`   | Domain classification         | OpenAlex ML classification |
| `keywords`         | Author-supplied keywords      | Crossref, repositories     |
| `concepts`         | Associated concepts/tags      | OpenAlex ML extraction     |
| `sdgs`             | Sustainable Development Goals | Future ML enrichment       |

**Primary Source:** OpenAlex AI/ML enrichment

---

## 9. Funding

| Canonical Field | OpenAlex Field | Crossref Field | Description                  |
| --------------- | -------------- | -------------- | ---------------------------- |
| `funders`       | `funders`      | `funder`       | Funding organization details |

**Structure:** `{name, doi, country}`

**Primary Source:** OpenAlex + Crossref

---

## 10. Conference Metadata

| Canonical Field    | OpenAlex Field | Crossref Field           | Description              |
| ------------------ | -------------- | ------------------------ | ------------------------ |
| `event_name`       | -              | `event.name`             | Conference/event name    |
| `event_acronym`    | -              | `event.acronym`          | Event acronym            |
| `event_location`   | -              | `event.location`         | Event location           |
| `event_start_date` | -              | `event.start.date-parts` | Event start date         |
| `event_end_date`   | -              | `event.end.date-parts`   | Event end date           |
| `event_sponsor`    | -              | `event.sponsor`          | Sponsoring organizations |

**Primary Source:** Mostly Crossref

---

## 11. Links & URLs

| Canonical Field    | OpenAlex Field     | Crossref Field | Description                  |
| ------------------ | ------------------ | -------------- | ---------------------------- |
| `source_url`       | `source_url`       | `URL`          | Source repository URL        |
| `landing_page_url` | `landing_page_url` | `URL`          | Publisher landing page       |
| `pdf_url`          | -                  | -              | Direct PDF link              |
| `repository_url`   | -                  | -              | Institutional repository URL |

---

## 12. Abstract & Full Text

| Canonical Field | OpenAlex Field | Crossref Field | Description                     |
| --------------- | -------------- | -------------- | ------------------------------- |
| `abstract`      | `abstract`     | `abstract`     | Publication abstract            |
| `full_text_url` | -              | -              | URL to full text (if available) |

**Availability:** Crossref provides abstracts for ~30% of records; OpenAlex retrieves where available.

---

## Data Flow Summary

```
OpenAlex API    Crossref API    Repositories
      ↓              ↓                ↓
      └──────────────┴────────────────┘
                     ↓
         Raw Record Collection
                     ↓
         Source-Specific Normalization
                     ↓
         Canonical Schema Mapping
                     ↓
         Deduplication (DOI matching)
                     ↓
         Final Publication Record
```

---

## Implementation Notes

- **DOI Normalization:** All DOIs normalized to lowercase, prefixes removed
- **Date Handling:** Store as `[YYYY, MM, DD]` arrays for consistency
- **Deduplication:** Primary key is normalized DOI; fallback to title + author matching
- **Missing Fields:** Use `null` for unavailable data (not empty strings)
- **Validation:** Required fields: `doi` or (`title` + `author_count`)
