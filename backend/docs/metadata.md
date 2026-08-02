# Publication Metadata Schema

Canonical schema for normalizing research publication metadata from multiple sources (OpenAlex, Crossref, repositories).

The merge uses a configurable field-level source policy. The schema describes
where evidence can come from; it does not mean every listed source has equal
authority for every field.

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

**Source signal:** OpenAlex and Crossref both provide useful venue evidence;
the merge policy chooses the final scalar value and logs conflicts.

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

**Source signal:** OpenAlex provides structured affiliation/country evidence;
local repositories provide national provenance and local affiliation text.

---

## 6. Impact Metrics

| Canonical Field   | OpenAlex Field           | Crossref Field           | Description                    |
| ----------------- | ------------------------ | ------------------------ | ------------------------------ |
| `citation_count`  | `cited_by_count`         | `is-referenced-by-count` | Number of citations            |
| `reference_count` | `referenced_works_count` | `reference-count`        | Number of references           |
| `fwci`            | `fwci`                   | -                        | Field-Weighted Citation Impact |

**Note:** OpenAlex and Crossref citation/reference counts can describe different
coverage. The public final dataset keeps best-available counts, while
source-specific count values are written to `publication_count_audit.csv`.

---

## 7. Open Access

| Canonical Field    | OpenAlex Field     | Crossref Field | Description                             |
| ------------------ | ------------------ | -------------- | --------------------------------------- |
| `is_open_access`   | `is_oa`            | -              | Open access status                      |
| `oa_status`        | `oa_status`        | -              | OA status (gold, green, hybrid, bronze) |
| `landing_page_url` | `landing_page_url` | `URL`          | Publisher landing page                  |
| `pdf_url`          | -                  | -              | Direct PDF URL (if available)           |

**Source signal:** OpenAlex is the main structured open-access source.

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

**Source signal:** OpenAlex supplies analytical topics/concepts; local keywords
should be treated as separate repository/author evidence.

---

## 9. Funding

| Canonical Field | OpenAlex Field | Crossref Field | Description                  |
| --------------- | -------------- | -------------- | ---------------------------- |
| `funders`       | `funders`      | `funder`       | Funding organization details |

**Structure:** `{name, doi, country}`

**Source signal:** Crossref and OpenAlex can both contribute funding evidence;
the merge policy and conflict logs determine final values.

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

**Source signal:** Mostly Crossref; OpenAlex/local values may be supporting
evidence when available.

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
         Field-Policy Merge + Conflict Log
                     ↓
         Final Publication Record + Audit Sidecars
```

---

## Implementation Notes

- **DOI Normalization:** All DOIs normalized to lowercase, prefixes removed
- **Date Handling:** Store as `[YYYY, MM, DD]` arrays for consistency
- **Deduplication:** Auto-merge by normalized DOI or source record ID; title/year/author candidates require manual review
- **Field policy:** Configurable source order for scalar fields, with completeness tie-breaking
- **Audit sidecars:** Reference payloads and source-specific count values are kept outside the public final CSV
- **Missing Fields:** Use `null` for unavailable data (not empty strings)
- **Validation:** Required fields: `doi` or (`title` + `author_count`)
