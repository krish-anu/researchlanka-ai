# Metadata Enrichment Strategy

## Primary Collection Source

OpenAlex is the primary collection backbone because it has strong affiliation,
topic, open-access, and citation metadata. It is not treated as an automatic
winner for every conflicting field in the implemented merge.

Provides:

- DOI
- Title
- Publication Date
- Authors
- Institutions
- Topics
- Concepts
- Citations
- OA Information

## Crossref Enrichment Fields

### Venue Metadata

- ISSN
- Volume
- Issue
- Page
- Article Number

### Conference Metadata

- Event Name
- Event Location
- Event Acronym
- Event Sponsor

### Funding Metadata

- Funder Name
- Funder DOI
- Funder Award

### Rights Metadata

- License URL
- License Version

### Citation Metadata

- Reference Count
- Reference List

## Review Before Overwrite

OpenAlex coverage is already strong for these fields, but conflicts should
still be reviewed before any overwrite:

- DOI
- Title
- Authors
- Publisher
- Publication Year



PUBLICATION_TYPES = [
    "Journal Article",
    "Conference Paper",
    "Book Chapter",
    "Book",
    "Preprint",
    "Review Article",
    "Dataset",
    "Report",
    "Thesis",
    "Reference Work",
    "Other"
]
