# Frontend Requirements

Week 1 deliverable (Gishan Bandara): frontend requirements for researchers,
universities, and policymakers. This informs the React interface wireframes
(Week 2) and the eventual publication/researcher/institution pages and
dashboards (Weeks 7-8).

## User Personas

### 1. Researcher

Wants to understand their own publication footprint, find related work, and
discover collaborators.

- Search for their own publication record by name or ORCID and correct
  obvious misattributions (flagging, not editing -- data stays
  pipeline-owned).
- View a personal profile page: publication list, citation counts over
  time, co-author network, research topics they publish in.
- Run semantic search across the full corpus to find related work.
- See recommended related publications on a given publication page.
- Filter/search publications by year, type, topic, institution, journal.
- Export a personal publication list (CSV/BibTeX-style) for CVs and grant
  applications.

### 2. University (research office / administrator)

Wants an institution-level view of research output, impact, and
collaboration reach, for internal reporting and benchmarking.

- Institution profile page: total publications, citation counts,
  productivity trend over time, open-access share.
- Department/faculty breakdown where affiliation data supports it.
- Ranked list of most active researchers and most-cited publications at
  the institution.
- Institution-level collaboration network (which institutions/countries
  they co-publish with).
- Compare productivity/citation trends against 1-2 other institutions.
- Filter by publication type (journal article, conference paper, thesis).

### 3. Policymaker (NSF / UGC / ministry-level)

Wants a national-level picture of research output, emerging fields, and
gaps, to inform funding and policy decisions.

- National dashboard: publication counts and trends over time, by field
  and by institution.
- Emerging vs. declining research topics (from topic modelling and trend
  analysis).
- National collaboration network: which institutions and countries
  Sri Lankan research connects to.
- Field-level breakdown to spot underrepresented research areas.
- Downloadable summary charts/tables for reports (image/CSV export from
  Plotly views).
- No login/auth requirement for this read-only, aggregate view (public
  dashboard).

## Shared Cross-Cutting Requirements

- **Search & filtering**: full-text/semantic search plus structured
  filters (year range, publication type, institution, topic, open-access
  status) available on every listing page.
- **Publication detail page**: title, authors (linked to researcher
  profiles where resolved), abstract, DOI, venue, citation count, topics,
  related/recommended publications, source repository provenance.
- **Researcher profile page**: identity (name, ORCID if known),
  affiliation history, publication list, citation trend, co-author
  network, topics.
- **Institution profile page**: as above at institution level.
- **Visualizations** (Plotly for charts, Cytoscape.js for networks):
  - Time-series: publications/citations per year.
  - Bar/treemap: publications by topic or institution.
  - Network graph: collaboration between authors/institutions/countries,
    with zoom, filter-by-institution, and node-click-to-profile.
- **Data provenance and confidence**: every record should show which
  source(s) it came from (OpenAlex, Crossref, institutional repository,
  SLJOL) and flag low-confidence entity resolution or classification
  results rather than presenting them as certain.
- **Performance**: search and profile pages should respond within a few
  seconds against the full consolidated dataset; heavy analytics
  (network layout, forecasting) can load asynchronously with a loading
  state.
- **Responsiveness**: usable on desktop and tablet at minimum, per the
  Week 9 "test frontend responsiveness" task.
- **No authentication required for MVP** (read-only public platform);
  revisit if personal researcher-editing features are added later.

## Out of Scope for MVP

- User accounts, login, or editable researcher-claimed profiles.
- Real-time data ingestion (updates run on a scheduled batch, per Week 9's
  "configure scheduled data updates").
- Full-text access to papers (metadata and links to source only; the
  platform is not a document repository).

## Traceability to the 10-Week Plan

| Requirement area | Delivered in |
|---|---|
| Wireframes | Week 2 |
| Publication search/filtering, recommendations | Week 7-8 |
| Researcher/institution profile pages | Week 8 |
| Dashboards (Plotly), collaboration network (Cytoscape.js) | Week 8 |
| Usability testing, responsiveness fixes | Week 9-10 |
