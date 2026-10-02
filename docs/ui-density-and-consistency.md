# UI density and consistency

Recommendations only. No interface code is changed by this note.

Source: a pass over the current frontend, checked against the nextlevelbuilder UI/UX Pro Max skill already in this repo (`.claude/skills/ui-ux-pro-max`). The matching product style is **Data-Dense Dashboard** (`styles.csv`, style id `data-dense-dashboard`): KPI row, compact cards, 12px card padding, 8px grid gap, 14px chrome type, sticky filters, and a 240px labeled sidebar. The skill’s auto design-system for “academic portfolio” (navy palette, EB Garamond, masonry project grid) does not fit this product. Keep the existing forest, paper, and turmeric tokens in `frontend/src/app/globals.css`.

## Decision: main navigation stays open

The desktop rail (`Explore`, `People & places`, `Connections`, `Trust`) is already 240px (`.app-rail` in `globals.css`). That is the skill’s `--sidebar-width`. Navigation items already carry an icon and a text label, which the skill requires (`nav-label-icon`). Collapsing that rail to an icon strip would hide the labels and make the sections harder to scan.

Leave the main rail at 240px. Do not add a Narrow control to it. Mobile already uses a drawer.

The publications Refine column is a filter, not primary navigation. Its existing Narrow control can stay.

What to shorten in the rail is the footer sentence in `SiteNav.tsx` (“Signed in. Public figures are unchanged…” / “Explore accepted AI-related publications from Sri Lanka.”). A role badge is enough. Move any scope statement to the existing AI-collection note.

## 1. Search fields are too long

| Surface | Current width | File |
| --- | --- | --- |
| Global top bar | `max-w-xl` (36rem) inside a full-width bar | `SiteNav.tsx` `SiteSearchBar` |
| Publications, researchers, institutions | The `SearchBox` is a block and stretches the content column (main max 1500px) | those pages + `SearchBox.tsx` |

A directory search should read as a tool, not a banner. Cap every `SearchBox` at **40rem** (640px), left-aligned with the content. Keep the global bar at **32rem**.

The field and the Search button do not share a height. The input row is `py-1.5` and 14px type; the button is `h-11` (44px) and forces the bar tall (`SearchBox.tsx`). Use the toolbar height in section 2 for both.

Placeholders that already name the page can stay (“Search publications by title, author, DOI…”). Drop the researchers hint “Matches the display name on publication records.” The placeholder “Search researchers...” already says what the field does.

## 2. One button size

`Button` defines `sm` (44px, 14px type) and `md` (48px). Every call site uses `sm`. `md` is unused.

Other controls ignore that scale:

| Control | Height | Type | Where |
| --- | --- | --- | --- |
| `Button` `sm` | 44px | 14px (`text-sm`, not the token) | Search, Apply, Clear, Download, Refine, Narrow, auth, admin |
| Pagination links | about 28px (`py-1`, `min-w-9`) | 14px | `Pagination.tsx` |
| Theme toggle | 32×32 | icon | `globals.css` `.theme-toggle` |
| Account trigger | about 32px (`py-1.5`) | 14px | `AccountMenu.tsx` |
| Chart / Table segments | 44px | 14px | `.chart-segments` |
| Year chips and facet rows | 44px | 14px | `.analytics-year-chip`, refine rows |
| Nav items | about 44px (`padding: 12px 13px`) | inherited 16px | `.nav-item` |

Proposed scale, still meeting a 44px touch target on small screens:

- **Toolbar** (default): 36px tall, 14px label, 12px horizontal padding. Use it for Search, Apply, Clear, Download, Refine, Narrow, pagination, year chips, and chart view switches on viewports ≥1024px.
- **Touch**: the same controls become 44px below 1024px.
- **Icon**: 36×36 with an accessible name (theme, close). Expand the hit area to 44px on touch.
- Retire `md`, or reserve it for the single auth submit on login and register.

Pagination page numbers should use the toolbar height so Previous / 1 / Next line up with Download and Sort on the same row.

## 3. Field and institution dropdowns

`AnalyticsFiltersForm.tsx` already filters with `includes` and auto-submits on an exact pick. Three gaps remain:

1. **The list stays closed until the user types.** On focus, show the fields that exist in the current selection, ordered by publication count, capped at 8. Typing then narrows that list.
2. **Ranking is alphabetical, then truncated.** “a” returns the first eight alphabetical contains-matches, not the closest names. Rank in this order: starts with the query, then a word inside the name starts with the query, then contains. Keep the cap of 8.
3. **Options are the global field list**, passed from each page as `fields.value.data.map(f => f.label)`. A year or institution filter can still offer a field that has no rows in that selection, and the page then shows an empty chart. Build the list from fields (and institutions) that have a count **in the current filters, excluding the field or institution being chosen**. Hide zero-count labels. If the selected value falls out of the list, keep it visible so the user can clear it.

Same rules for the institution combobox. Do not add a research-field filter back to the publications Refine column.

Search suggestions (`SearchBox.tsx`) should keep returning only types the page asked for. On a filtered directory, do not suggest a record the current filters would exclude. If the suggestion API cannot do that, say so in the empty row (“No matches in this selection”) and offer the existing “search all” action. Do not invent extra suggestion types.

## 4. Copy to remove

Keep a sentence only when it changes how a number is read (denominator, snapshot limit, disagreement). Remove the rest.

| Remove or shorten | Where |
| --- | --- |
| Rail footer explainer | `SiteNav.tsx` |
| “Use the search on this page to filter the current directory.” | mobile drawer, same file |
| Researchers search hint | `researchers/page.tsx` |
| Page intro that restates the title (“Explore researchers through…”, “Explore Sri Lankan research publications…”, “Explore the partnerships…”) | `PageIntro` on researchers, publications, collaboration. Keep a one-line scope only on overview and data quality. |
| Chart subtitle that repeats the heading, plus a second insight sentence | `ChartPanel` `description` and `insight`. One line under the title is enough. |
| “Charts for the institutions on this page — open when you want visual comparison.” | institutions landscape disclosure |
| “Distinct from NMF topic-model filters.” | topics page, unless that page still shows both systems at once |
| “Visitors are not listed — an unsigned visitor has no account…” | admin users |
| Repeated AI-scope paragraph on every route | `AIScopeNote` already collapses after dismiss. Default the compact chip on every page except overview. |

Keep: empty-state recovery, data-quality limitations, flag and merge warnings, and the overview AI-collection note.

## 5. Type scale

Tokens already exist in `globals.css`: h1 30, h2 22, h3 17, body 16, body-sm 14, label 12. Components also use raw Tailwind `text-xs` (12px) and `text-sm` (14px), and chart CSS sets its own 16 / 12 / 14 sizes. Those do not share line-height or weight with the tokens.

Use only the tokens:

| Role | Token | Size | Use |
| --- | --- | --- | --- |
| Page title | `text-h1` | 24px on dashboards, 30px on profiles | one per page |
| Section title | `text-h2` | 18px | directory headings and chart titles (chart titles are 16px today) |
| Body | `text-body-md` | 16px | abstracts, limitations, empty-state titles |
| Chrome | `text-body-sm` | 14px | buttons, table cells, filter labels, nav items, card meta |
| Eyebrow | `text-label` | 12px, weight 600 | nav section labels, stat labels, “as of” |
| Identifiers | `text-mono` | 13px | DOI, ids |

Replace `text-xs` and `text-sm` in `StatTile`, `QualityFlags`, `QualityCompleteness`, `CollaborationNetwork`, `SiteNav`, `ResearchPanels`, chart footnotes, and `Button`. Nav item type should be 14px, not the 16px body default.

KPI figures can stay large (`stat-value` is 32px). Supporting lines under them should be 14px, not a mix of 12 and 14.

## 6. Cards should fit their content

Data-dense targets: card padding **12px**, gap between cards **8px**, gap between page sections **16px**. Current values are looser:

| Surface | Now | Change |
| --- | --- | --- |
| `.stat-tile` | padding 21px, gap 9px, radius 13px, value 32px | padding 12px, gap 4px, radius 8px (the shared `--radius-md`). Keep the number large. |
| `.stat-grid` | gap 16px, min 180px | gap 8px |
| `.chart-panel` | padding 22px, plus a subtitle and an insight | padding 12px. Drop the second text line (section 4). |
| `.app-main` | padding 32px | 24px desktop, 16px below 768px |
| `.app-topbar` | min-height 76px | 56px once the search control is toolbar height |
| Plotly host | `padding-top: 28px` reserved for the modebar | keep the tool strip, but do not add a second empty band under it |
| Empty chart | one sentence inside a panel that still reserves a tall plot (`h-64` / `h-96`, or “No records in this selection.” in `RankingBarChart`, `TrendLineChart`, `InstitutionScatterChart`) | collapse to the panel header plus one line and, when filters are on, a Clear filters action. Do not draw empty axes. |
| `EmptyState` | already `px-4 py-4` | keep this as the only empty pattern. Point every “no data” path at it: charts, tables (`DataTable` “No data available.”), network (“No collaboration edges…”), and recent-publications (“No publications match…”). Title, one recovery sentence, one button. |
| Publication and researcher rows | already dense | leave the row layouts. Do not put them back in padded cards. |

Filtered-empty and never-had-data stay different sentences, which `emptyListState` in `Feedback.tsx` already does. Charts should call that helper instead of a unique one-liner so the recovery action is the same everywhere.

## 7. Page notes

- **Overview.** Tightest win. Stat tiles, chart panels, and story descriptions (`StorySection` in `page.tsx`) are the sparse cards. Shorten each section to a title and the chart.
- **Publications.** Search width (section 1). Refine order and the record layout can stay. Empty results already use `EmptyState`.
- **Researchers and institutions.** Same search cap. Drop the search hint. Landscape disclosures should not explain that the charts are optional.
- **Topics.** Keep the drill interaction. Shorten the NMF versus OpenAlex sentence if both are not on screen together.
- **Collaboration.** Network empty copy can become the shared empty state. Inspector type is `text-xs` in several places; move it to `text-body-sm` or `text-label`.
- **Data quality.** Keep limitation text. Apply the card padding and type rules so the page matches overview.
- **Profiles.** 30px titles are appropriate. Section descriptions that say “newest first” or “most frequent collaborators” can stay as one line. Empty co-author and field blocks should use `EmptyState`, not a bare sentence in a large panel.
- **Admin, account, login.** Same button and type rules. Admin explanations that describe the pipeline can stay; marketing-length role explanations can go (section 4).

## 8. Suggested order

1. Search max-width and shared control height.
2. Toolbar button size, then pagination and theme toggle.
3. Field and institution list: show on focus, rank matches, hide zero counts.
4. Delete the copy in section 4.
5. Swap raw `text-xs` / `text-sm` for tokens, and set chart titles to the section size.
6. Card padding, grid gap, and collapsed empty charts.

Do not change API contracts for the copy, type, or spacing work. The field dropdown change needs the current selection’s field counts. If that payload already exists on the page, use it. If it does not, add the smallest query the existing fields endpoint already supports, and skip values with a zero count.
