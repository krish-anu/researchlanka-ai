# Publication Categories

Common Crossref types map to the framework's canonical values as follows. The
authoritative complete type set and alias rules are in
`research_analytics/venues.py`.

| Crossref Type | Category |
|--------------|-----------|
| journal-article | journal_article |
| proceedings-article | conference_paper |
| book-chapter | book_chapter |
| book | book |
| posted-content | preprint |
| report | report |
| dissertation | thesis |
| dataset | dataset |

Unknown values become `unknown`. Source values remain available in provenance
fields; normalization must not silently discard the original evidence.
