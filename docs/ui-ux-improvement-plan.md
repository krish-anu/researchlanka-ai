# ResearchLanka — Overall UI/UX Improvement Plan

**Status:** Proposal only — no code changes in this document.  
**Scope:** Public analytics, search/browse, profiles, collaboration, data quality, account, and admin surfaces.  
**Audience:** Product + engineering implementing incremental UX work.  
**Design baseline to preserve:** Forest-green / warm-paper system in `frontend/src/app/globals.css`, fonts in `frontend/src/app/layout.tsx`, approved preview in `design-preview/researchlanka-ui-preview.html`.

---

## 1. What this app is (and what “better UX” means here)

ResearchLanka is a **read-only national AI-research analytics site**: overview dashboards, publication search, researcher/institution/topic directories, collaboration networks, data-quality disclosures, plus optional accounts (saved library / flags) and an admin console.

Personas (from `backend/docs/frontend_requirements.md`):

| Persona | Job to be done | UX priority |
|---|---|---|
| Policymaker / public | Trustworthy national picture in minutes | Clear scope, denominators, exportable charts |
| Researcher | Find self/related work, collaborators | Fast search, readable profiles, network drill-down |
| University office | Benchmark institutions | Compare flows, rankings + OA scatter, shareable links |
| Admin | Steward queues without confusing corpus vs app state | Separated metrics, obvious actions, low cognitive load |

**Guiding principles (keep these while modernising):**

1. **Interpretability over decoration** — every number states *what*, *over what*, and *as of when*.
2. **Provenance is product** — AI collection scope, snapshot date, and source limitations stay visible.
3. **Chart ↔ table parity** — visualisations never be the only way to read a figure (already started in `ChartPanel`).
4. **One job per section** — reduce competing CTAs, repeated stats, and filter chrome.
5. **Small effects that explain; big visuals that answer questions** — motion supports orientation; charts answer “what changed / who leads / how connected”.

---

## 2. Current strengths (do not throw away)

| Strength | Where it lives | Keep / extend |
|---|---|---|
| Semantic colour tokens + dark theme | `globals.css` `:root` / `[data-theme="dark"]` | Keep tokens; avoid raw hex in new UI |
| Display / body / mono font roles | `layout.tsx` Archivo + IBM Plex | Keep; raise base body size slightly |
| Skip link, focus ring, reduced-motion | `layout.tsx`, `globals.css` | Keep; expand keyboard paths in network |
| Chart/table toggle | `components/ui/ChartPanel.tsx` | Make default pattern on every plot |
| AI-scope banner | `SiteNav.tsx` → `AIScopeNote` | Keep; make dismissible + remembered |
| Machine (AI-generated) tint | `.machine-panel`, `StatTile.machine` | Keep as trust signal |
| Search combobox a11y | `SearchBox.tsx` | Keep pattern; improve empty/error states |
| Lazy Plotly + shared import | `PlotlyChart.tsx` | Keep; improve loading skeleton |
| Cytoscape size-metric + community colour rules | `CollaborationNetwork.tsx` | Keep interpretability rules; improve mobile UX |
| GET forms for filters | `AnalyticsFilters`, `FilterControls` | Keep no-JS filtering; polish layout |
| Admin corpus vs workspace separation | `app/admin/page.tsx` | Keep conceptual split; clarify visually |

---

## 3. Improvement map: small → large

Each item is **Current → Change → Code touchpoints**. Priority: **P0** (trust / clarity), **P1** (ease of use), **P2** (polish / modern feel), **P3** (larger redesign).

---

### A. Micro-interactions & visual polish (small)

#### A1. Base type size too small for dense analytics
| | |
|---|---|
| **Current** | `body { font-size: 14px }` in `globals.css` |
| **Change** | Raise default to **16px** (`text-body-md`); keep dense tables at `text-body-sm` / 13–14px explicitly |
| **Why** | WCAG & modern dashboard readability; 14px body hurts long sessions |
| **Code** | `frontend/src/app/globals.css` `@layer base`; spot-check `DataTable`, filters |
| **Priority** | P0 |

#### A2. Hero / brand micro-type hard to read
| | |
|---|---|
| **Current** | Hero eyebrow `text-[9px]`; brand tagline `font-size: 8px` (`.brand-tagline`) |
| **Change** | Floor micro-labels at **10–11px** with stronger contrast (`text-muted` → slightly darker ink-secondary on light) |
| **Code** | `PageIntro.tsx` `ResearchHero`; `globals.css` `.brand-tagline`, `.page-eyebrow`, `.ai-scope` |
| **Priority** | P0 |

#### A3. Buttons feel flat and inconsistent
| | |
|---|---|
| **Current** | `.button` / `.button-primary` + ad-hoc Tailwind on forms |
| **Change** | Single button API: primary / secondary / ghost / danger; consistent height **36–40px**; loading state for GET-less actions |
| **Code** | Extract `components/ui/Button.tsx`; replace classes in `ChartPanel`, `AnalyticsFilters`, `AuthForm`, admin panels |
| **Priority** | P1 |

#### A4. Hover / press feedback sparse
| | |
|---|---|
| **Current** | Mostly border colour hover (e.g. `.publication-card`); few transitions (good for reduced-motion, weak for feel) |
| **Change** | Short **120–180ms** transitions on colour/shadow for cards, nav, chips; respect `prefers-reduced-motion` (already global) |
| **Code** | `globals.css` utilities `.interactive`, `PublicationCard.tsx`, `.nav-item` |
| **Priority** | P2 |

#### A5. Theme toggle discoverability
| | |
|---|---|
| **Current** | Desktop: top bar; mobile: inside drawer only |
| **Change** | Keep desktop placement; add theme control to **mobile app bar** (next to search) |
| **Code** | `SiteNav.tsx` mobile header; `ThemeToggle.tsx` |
| **Priority** | P2 |

#### A6. Skeleton → content continuity
| | |
|---|---|
| **Current** | Generic `Skeleton` blocks in Suspense |
| **Change** | Chart-shaped skeletons matching `chart-panel` height; announce “Loading …” with `aria-busy` on panel |
| **Code** | `Feedback.tsx` `Skeleton`; wrap in `ChartPanel` loading variant; `app/page.tsx` Suspense fallbacks |
| **Priority** | P1 |

#### A7. Empty vs error vs zero-filter confusion
| | |
|---|---|
| **Current** | Good `ApiErrorPanel` / `EmptyState`, but recovery CTAs vary |
| **Change** | Standardise three states with **primary recovery**: Retry (error), Clear filters (empty), Browse all (zero query) |
| **Code** | `Feedback.tsx`; use on publications, researchers, institutions, topics pages |
| **Priority** | P1 |

---

### B. Navigation, IA & wayfinding (medium)

#### B1. Flat nav of 7–8 peers overwhelms first-time visitors
| | |
|---|---|
| **Current** | Single “Workspace” list: Overview → … → Data quality (+ Admin) |
| **Change** | Group into **Explore** (Overview, Publications, Topics), **People & places** (Researchers, Institutions), **Connections** (Collaboration), **Trust** (Data quality) |
| **Code** | `SiteNav.tsx` `NAV_LINKS` + section headers; `globals.css` nav section styles |
| **Priority** | P1 |

#### B2. Breadcrumb is label-only, not navigable
| | |
|---|---|
| **Current** | Top bar: `Workspace / {section}` text |
| **Change** | Real breadcrumbs: **Overview › Institution › University of …**; clickable ancestors |
| **Code** | New `components/layout/Breadcrumbs.tsx`; use in `SiteSearchBar` + detail pages (`institutions/[...key]`, `researchers/[...key]`, `publications/[...key]`, `topics/[...key]`) |
| **Priority** | P1 |

#### B3. AI scope note repeats on every public page
| | |
|---|---|
| **Current** | Always-on `.ai-scope` strip |
| **Change** | Keep on Overview + first visit; elsewhere collapse to compact chip in top bar or allow **Dismiss for session** (`sessionStorage`) |
| **Code** | `SiteNav.tsx` `AIScopeNote`; optional `components/ui/ScopeChip.tsx` |
| **Priority** | P1 |

#### B4. Overview page stacks hero + intro + filters + stats (cognitive overload)
| | |
|---|---|
| **Current** | `PageIntro` + `ResearchHero` + filters + 4 tiles + many charts (`app/page.tsx`) |
| **Change** | **Merge** intro + hero into one composition; put filters in a sticky **control bar**; lead with 4 KPIs then “story” sections (trend → fields → institutions → network → recent) |
| **Code** | `PageIntro.tsx`, `app/page.tsx`, `globals.css` `.research-hero` |
| **Priority** | P0 |

#### B5. Duplicate search surfaces
| | |
|---|---|
| **Current** | Global top search + page-local `SearchBox` on publications/institutions/researchers |
| **Change** | Global search = **cross-entity**; page search = contextual (hide global duplicate on `/publications` when page search is primary, or sync query params both ways) |
| **Code** | `SiteSearchBar`, page headers, `SearchBox` `targetPath` / `suggestionTypes` |
| **Priority** | P1 |

#### B6. Account & admin feel bolted onto public shell
| | |
|---|---|
| **Current** | Same rail + AI scope hidden on `/account` `/admin`; otherwise same chrome |
| **Change** | Slightly denser **admin theme strip** (eyebrow “Administration”); account as “My workspace” with simpler nav subset |
| **Code** | `app/admin/layout.tsx`, `AdminNav.tsx`, `app/account/layout.tsx` |
| **Priority** | P2 |

---

### C. Filtering, search & task flows (ease of use)

#### C1. Analytics filters look like a raw form row
| | |
|---|---|
| **Current** | `.analytics-filters` inline labels; Apply / Reset |
| **Change** | **Filter bar card**: year range as dual control or year chips (2016–now presets); field as searchable select; show “Filters applied” summary inline |
| **Code** | `AnalyticsFilters.tsx`, `globals.css` `.analytics-filters`; reuse on Overview, Collaboration, Institutions, Data quality |
| **Priority** | P0 |

#### C2. Active filters chips exist but are easy to miss
| | |
|---|---|
| **Current** | `ActiveFilters` below filter forms |
| **Change** | Sticky chip row under top bar; one-click clear-all; human labels (“Open access”, not `is_oa=true`) |
| **Code** | `FilterControls.tsx` `ActiveFilters`; layout sticky class |
| **Priority** | P1 |

#### C3. Collaboration controls split across two forms
| | |
|---|---|
| **Current** | `AnalyticsFilters` + separate scope/min_weight/limit form (`collaboration/page.tsx`) |
| **Change** | **One** “Network controls” panel: year/field + scope + density (min weight, max nodes) + Apply |
| **Code** | `app/collaboration/page.tsx`; optionally extend `AnalyticsFilters` with `extraControls` slot |
| **Priority** | P0 |

#### C4. Publications facet sidebar heavy on mobile
| | |
|---|---|
| **Current** | `xl` grid with aside facets always in DOM |
| **Change** | Mobile: facets in **drawer / bottom sheet**; show “Filters (n)” badge |
| **Code** | `publications/page.tsx`, `FacetPanel.tsx`, new `FilterDrawer` client wrapper |
| **Priority** | P1 |

#### C5. Search suggestions lack “no results” and type grouping
| | |
|---|---|
| **Current** | List of typed chips; silent fail on API error |
| **Change** | Group by type (Publications / Researchers / Institutions); empty state “No matches — search all publications”; subtle error toast |
| **Code** | `SearchBox.tsx` |
| **Priority** | P1 |

#### C6. Compare institutions is a hidden secondary flow
| | |
|---|---|
| **Current** | Link button on institutions directory |
| **Change** | From ranking charts / cards: **“Compare”** checkbox (up to 3) → sticky “Compare selected” CTA → `/institutions/compare?...` |
| **Code** | `institutions/page.tsx`, `institutions/compare/page.tsx`, small client `CompareTray` |
| **Priority** | P1 |

#### C7. Saved library / flags under-explained for guests
| | |
|---|---|
| **Current** | Auth copy is good on login; save/flag appear on records |
| **Change** | Guest sees soft prompt once: “Sign in to save & flag” near `RecordActions` |
| **Code** | `RecordActions.tsx`, `login/page.tsx` copy already strong — wire contextual CTA |
| **Priority** | P2 |

---

### D. Interpretability of numbers & copy (trust)

#### D1. KPI tiles lack “as of” and trend spark
| | |
|---|---|
| **Current** | Value + caption; `SnapshotNote` sits below grid |
| **Change** | Put **snapshot date inside** first tile row or as shared subtitle; optional mini sparkline for publications over time (links to trend section) |
| **Code** | `StatTile.tsx`, `app/page.tsx`, `Provenance.tsx` `SnapshotNote` |
| **Priority** | P0 |

#### D2. Denominator language inconsistent
| | |
|---|---|
| **Current** | Mix of “accepted AI records”, “this selection”, “collection” |
| **Change** | Glossary of 5 phrases used everywhere; chart descriptions always say “of selected AI publications” when filters apply |
| **Code** | Copy pass: `PageIntro` titles, chart `description` props in `ResearchPanels.tsx`, publications stats |
| **Priority** | P0 |

#### D3. Open-access % without absolute counts
| | |
|---|---|
| **Current** | Ratio-only on tiles |
| **Change** | Show **“42% (1,204 of 2,867)”** pattern where totals exist |
| **Code** | `format.ts` helper; `StatTile` optional `detail`; Overview + publications |
| **Priority** | P1 |

#### D4. Chart titles are poetic; axes need plainer language
| | |
|---|---|
| **Current** | e.g. “The AI research landscape”, “AI research is a shared endeavour” |
| **Change** | Keep poetic **section** titles; add plain **subtitle**: “Share of publications by primary field (top 5)” |
| **Code** | `ResearchPanels.tsx`, `app/page.tsx` `ChartPanel` props |
| **Priority** | P0 |

#### D5. Data quality page is long prose + charts
| | |
|---|---|
| **Current** | Limitations, disclosures, completeness charts |
| **Change** | Lead with **“Read this before citing”** 3 bullets; accordion for full limitations; “How to cite a figure” mini guide |
| **Code** | `app/data-quality/page.tsx`, `QualityCompleteness.tsx` |
| **Priority** | P1 |

#### D6. Machine / AI synthesis vs harvested metadata
| | |
|---|---|
| **Current** | Violet panels exist; not all synthesis uses them |
| **Change** | Audit every AI-ish surface; legend in footer or data-quality: “Violet = model-generated” |
| **Code** | `MachinePanel`, admin AI review cards, any profile summaries |
| **Priority** | P1 |

---

### E. Charts & visualisation (medium → large)

#### E1. Unify chart chrome
| | |
|---|---|
| **Current** | Plotly modebar floating above; custom segments for chart/table |
| **Change** | Always: title, plain subtitle, insight line (1 sentence), view toggle, download, optional “How to read” |
| **Code** | Extend `ChartPanel.tsx`; theme via `charts/theme.ts` |
| **Priority** | P0 |

#### E2. Trend chart: clearer dual series
| | |
|---|---|
| **Current** | Total + OA secondary (`TrendLineChart.tsx`) |
| **Change** | Default **area + line**; legend with exact last-year values; optional “% OA” toggle; annotate major policy years if known (optional later) |
| **Code** | `TrendLineChart.tsx`, `TrendPanel` in `ResearchPanels.tsx` |
| **Priority** | P1 |

#### E3. Field distribution: donut alone is weak for many categories
| | |
|---|---|
| **Current** | Top-5 + other (`DistributionChart.tsx`) |
| **Change** | Segmented control: **Share (donut) | Counts (horizontal bars)** — bars better for comparison; keep table |
| **Code** | `DistributionChart.tsx`, `FieldDistributionPanel` |
| **Priority** | P1 |

#### E4. Heatmap readability
| | |
|---|---|
| **Current** | `ActivityHeatmap` with printed counts |
| **Change** | Stronger sequential ramp from tokens; row sort by total; tooltip with field+year+count; colour-blind safe check already via tokens — document in UI |
| **Code** | `ActivityHeatmap.tsx`, `theme.ts` |
| **Priority** | P1 |

#### E5. Institution scatter interpretability
| | |
|---|---|
| **Current** | Output vs OA share (`InstitutionScatterChart.tsx`) |
| **Change** | Quadrant labels (“High output · High OA”); click → institution profile; size legend explicit |
| **Code** | `InstitutionScatterChart.tsx`, `InstitutionAccessibilityPanel` |
| **Priority** | P1 |

#### E6. Ranking bars: more scannable
| | |
|---|---|
| **Current** | `RankingBarChart.tsx` |
| **Change** | Truncate long labels with tooltip; value labels at bar end; link bars to profiles where keys exist |
| **Code** | `RankingBarChart.tsx`; Overview + institutions usage |
| **Priority** | P2 |

#### E7. Collaboration network — biggest visualisation UX debt
| | |
|---|---|
| **Current** | Full Cytoscape canvas; size metric select; brokers table; high a11y risk on graphs |
| **Change** | **Desktop:** guided “Explore” mode — select node → side inspector (metrics, top partners, Open profile). **Mobile:** default to **table / adjacency** first; graph optional behind “Show map”. Add keyboard move controls (skill guidance). Reset + PNG/CSV already conceptually present — surface them in one toolbar. |
| **Code** | `CollaborationNetwork.tsx`, `NetworkMetrics.tsx`, `NetworkPanel`, `collaboration/page.tsx` |
| **Priority** | P0 |

#### E8. Overview network preview too heavy
| | |
|---|---|
| **Current** | Full `NetworkPanel` mid-overview |
| **Change** | Compact preview (fewer nodes) + strong CTA to `/collaboration`; or summary metrics only + thumbnail |
| **Code** | `app/page.tsx`, `NetworkPanel` props (`limit`, `compact`) |
| **Priority** | P1 |

#### E9. “Insight captions” under charts
| | |
|---|---|
| **Current** | Static muted footnotes |
| **Change** | Compute 1-line insight when data allows: “Output rose ~X% since 2016; OA share is Y%.” (client or server derive in `services/derive.ts`) |
| **Code** | `derive.ts`, panel components |
| **Priority** | P2 |

#### E10. Export UX
| | |
|---|---|
| **Current** | CSV/download links scattered; Plotly PNG in modebar |
| **Change** | Per-panel **Export** menu: CSV / PNG / “Copy link with filters” |
| **Code** | `ChartPanel` action slot; `DownloadLink`; share URL helper from current query |
| **Priority** | P2 |

---

### F. Page-level composition (large)

#### F1. Overview (`app/page.tsx`)
| Current | Proposed |
|---|---|
| Intro + hero + filters + KPIs + 2-col charts + rankings + heatmap + full network + recent pubs | **Single hero** → sticky filters → KPI strip with snapshot → narrative sections with clear H2s → compact network teaser → recent pubs as cards option |
| Code focus | `page.tsx`, `ResearchPanels.tsx`, `PageIntro.tsx` |

#### F2. Publications (`app/publications/page.tsx`)
| Current | Proposed |
|---|---|
| Stats + search + sidebar filters + table/cards | Collapse duplicate stats when identical to Overview; results-first on mobile; sticky sort + view switcher; richer `PublicationCard` hierarchy (title → authors → field/year/OA) |
| Code focus | `PublicationCard.tsx`, `ViewSwitcher.tsx`, `FilterControls`, `FacetPanel` |

#### F3. Researchers / Institutions directories
| Current | Proposed |
|---|---|
| Search + charts + table/cards | **Directory-first**: search + view switcher + ranking; charts in “Insights” tab or collapsible so scan-mode users aren’t pushed past plots |
| Code focus | `researchers/page.tsx`, `institutions/page.tsx`, `ViewSwitcher.tsx` |

#### F4. Detail profiles (`*/[...key]/page.tsx`)
| Current | Proposed |
|---|---|
| Long vertical stacks | Sticky profile header (name, key metrics, actions); tabbed sections: Overview · Publications · Network · Topics; consistent `RecordActions` placement |
| Code focus | Detail pages; shared `ProfileHeader` component (new) |

#### F5. Topics (`topics/page.tsx`)
| Current | Proposed |
|---|---|
| Hierarchy + charts; NMF errors as data errors | Explain NMF vs taxonomy in plain language; progressive disclosure for model-unavailable; visual hierarchy Domain → Field → Subfield as tree or drill chips |
| Code focus | Topics pages + panels |

#### F6. Login / Register
| Current | Proposed |
|---|---|
| Clear copy + form | Add **visual of benefit** (saved library mock) without fake data claims; social proof not needed — keep trust-first |
| Code focus | `login/page.tsx`, `register/page.tsx`, `AuthForm.tsx` |

#### F7. Admin console
| Current | Proposed |
|---|---|
| Corpus vs queues already split | Status **health banner** (API up/down); queue cards as actionable tiles with counts + primary buttons; reduce table density on overview |
| Code focus | `admin/page.tsx`, `AdminNav.tsx`, `ActionResult.tsx` |

---

### G. Layout, responsive & performance (cross-cutting)

#### G1. Content max-width 1500px feels sparse on ultra-wide
| | |
|---|---|
| **Current** | `.app-main { max-width: 1500px }` |
| **Change** | Keep for dashboards; constrain **prose/detail** to ~72–80ch; use full width only for charts/network |
| **Code** | `globals.css`; profile/publication detail layouts |
| **Priority** | P2 |

#### G2. Mobile rail → app bar OK; chart overflow
| | |
|---|---|
| **Current** | Many charts fixed height; network heavy |
| **Change** | Horizontal scroll only inside chart hosts; touch tooltips; network table-first (E7) |
| **Code** | `PlotlyChart`, `CollaborationNetwork`, `.scroll-x` |
| **Priority** | P0 |

#### G3. Perceived performance
| | |
|---|---|
| **Current** | Lazy Plotly/Cytoscape good |
| **Change** | Prefer streaming/Suspense boundaries per section (already partly done); avoid blocking whole page on one slow panel |
| **Code** | Page-level `Suspense` boundaries; skeleton quality (A6) |
| **Priority** | P1 |

#### G4. Print / cite
| | |
|---|---|
| **Current** | Basic `@media print` hides nav/filters |
| **Change** | Print stylesheet includes snapshot date + filter summary in header |
| **Code** | `globals.css` `@media print`; small `PrintMeta` component |
| **Priority** | P3 |

---

### H. Accessibility (raise the floor)

| Issue | Change | Code |
|---|---|---|
| Icon-only controls | Ensure `sr-only` labels everywhere (mostly done) | Audit `NavIcons` usages, theme, mobile search |
| Chart colour-only encoding | Always dual-encode (pattern, label, table) | All charts + network |
| Focus trap only on mobile nav | Add same care to future filter drawers | `SiteNav` pattern reuse |
| Live regions | `aria-live="polite"` when filter results count updates | Publications results header |
| Contrast of muted text | Recheck `--muted` on `--page` / `--wash` | `globals.css` + `npm run check:palette` |
| Network keyboard | Focusable nodes / inspector, not drag-only | `CollaborationNetwork.tsx` |

**Priority:** P0 for contrast + network fallback; P1 for live regions.

---

### I. Motion system (modern feel without noise)

| Effect | Use | Avoid |
|---|---|---|
| Page section fade-in (subtle) | First paint of chart panels | Staggered cascades on every tile |
| Sticky filter bar shadow | When stuck | Parallax hero |
| Network highlight pulse | Selected node | Continuous ambient animation |
| Route transition | Optional opacity 100ms | Full-page slides |

Implement as CSS utilities in `globals.css`; gate with `prefers-reduced-motion` (already present).

**Priority:** P2.

---

## 4. “What should change to what” — component cheat sheet

| Component / file | From | To |
|---|---|---|
| `globals.css` body | 14px | 16px base; explicit dense sizes |
| `.ai-scope` | Always full strip | Contextual / dismissible |
| `.analytics-filters` | Loose form row | Card + presets + summary |
| `PageIntro` + `ResearchHero` | Two stacked blocks | One overview composition |
| `SiteNav` | Flat list | Grouped IA + better mobile theme |
| `SiteSearchBar` | Static section label | Navigable breadcrumbs |
| `ChartPanel` | Title + toggle + plot | + insight + export menu + how-to-read |
| `StatTile` | Big number | Number + absolute context + snapshot affinity |
| `SearchBox` | Flat suggestion list | Grouped types + empty/error |
| `AnalyticsFilters` | Year/field only | Shared filter shell for analytics routes |
| `CollaborationNetwork` | Graph-first | Inspector + mobile table-first |
| `NetworkPanel` on Overview | Full graph | Compact teaser |
| `ViewSwitcher` | Local only | Persist preference (`localStorage`) |
| `Feedback` Skeleton | Generic pulse box | Structure-matching skeletons |
| `ActiveFilters` | Below fold chips | Sticky, plain-language chips |
| Detail pages | Long scroll | Sticky header + tabs |
| Admin overview | Dense mixed tables | Health banner + queue action cards |

---

## 5. Suggested implementation phases

### Phase 1 — Trust & clarity (1–2 weeks)
- A1, A2, B4, C1, C3, D1, D2, D4, E1, E7 (table-first mobile), H contrast  
- Outcome: policymakers can cite figures with less confusion.

### Phase 2 — Ease of use (2–3 weeks)
- B1–B3, B5, C2, C4–C6, A6–A7, E2–E5, E8, F2–F4  
- Outcome: researchers complete search → profile → network without getting lost.

### Phase 3 — Modern polish (1–2 weeks)
- A3–A5, E6, E9–E10, I motion, G1, F7  
- Outcome: site feels contemporary without abandoning the forest-green system.

### Phase 4 — Larger bets (backlog)
- Profile tab IA, compare tray, print/cite pack, optional insight generation via `derive.ts`  
- Validate with 3–5 users per persona before building.

---

## 6. Success criteria (how we’ll know it worked)

| Metric | Baseline idea | Target |
|---|---|---|
| Time to first meaningful insight on Overview | Informal: many scrolls past hero | KPI + trend visible without scroll on laptop |
| Filter recovery | Users stuck with empty results | ≥1 clear CTA on every empty state |
| Mobile collaboration | Graph unusable | Table path completes task (find top partner) |
| Interpretability | Questions “of what?” | Spot-check: every KPI has denominator + snapshot |
| A11y | Palette check exists | Charts retain table mode; network has non-colour path |
| Brand | Forest green preview | No purple-on-white redesign; tokens stay source of truth |

---

## 7. Explicit non-goals (for this plan)

- Replacing Plotly/Cytoscape wholesale (unless network accessibility forces SVG subset later).
- Turning the public site into a marketing landing page (it is an analytics product).
- Editing pipeline-owned corpus from the UI.
- Dark-mode-only or glassmorphism restyle (contradicts approved brand).

---

## 8. File index (primary touchpoints)

```
frontend/src/app/globals.css
frontend/src/app/layout.tsx
frontend/src/app/page.tsx
frontend/src/app/publications/page.tsx
frontend/src/app/researchers/page.tsx
frontend/src/app/institutions/page.tsx
frontend/src/app/institutions/compare/page.tsx
frontend/src/app/topics/page.tsx
frontend/src/app/collaboration/page.tsx
frontend/src/app/data-quality/page.tsx
frontend/src/app/login/page.tsx
frontend/src/app/account/**
frontend/src/app/admin/**

frontend/src/components/layout/SiteNav.tsx
frontend/src/components/layout/PageIntro.tsx
frontend/src/components/layout/SiteFooter.tsx
frontend/src/components/analytics/AnalyticsFilters.tsx
frontend/src/components/analytics/ResearchPanels.tsx
frontend/src/components/ui/ChartPanel.tsx
frontend/src/components/ui/StatTile.tsx
frontend/src/components/ui/Feedback.tsx
frontend/src/components/ui/ViewSwitcher.tsx
frontend/src/components/search/SearchBox.tsx
frontend/src/components/publications/FilterControls.tsx
frontend/src/components/publications/PublicationCard.tsx
frontend/src/components/network/CollaborationNetwork.tsx
frontend/src/components/network/NetworkMetrics.tsx
frontend/src/components/charts/*
frontend/src/services/derive.ts
frontend/src/services/format.ts
```

---

## 9. One-line summary

**Keep the forest-green trust system and chart/table honesty; fix type scale and filter clarity; regroup navigation; make Overview a single story; make collaboration interpretable on mobile; and layer modern micro-interactions and export/insight affordances last — always mapping every visual to a denominator, a snapshot, and a keyboard-reachable table.**
