# Administration UI and UX review

Review only. No application code was changed.

Scope: the administration console (`frontend/src/app/admin`, `frontend/src/components/admin`, and the shared shell in `frontend/src/app/globals.css` and `frontend/src/components/layout`). Guidance below comes from the current interface plus UI/UX Pro Max searches for a dense research-admin dashboard (minimal variance, subtle motion, high density), adaptive navigation, dashboard card style, and semantic color. Generic palette hits that would replace ResearchLanka’s forest-green tokens were rejected; they do not fit this product.

## What is already consistent

The console already sits on the public design tokens: paper page (`--page`), white cards (`--surface`), forest green (`--primary` `#287c58`), turmeric accent, violet for machine-generated content, and named status colors (`--good`, `--warning`, `--serious`, `--critical`). Cards share `.panel` (white surface, `--rule` border, 12px radius). The left rail is 240px and collapses on small screens. Admin tabs already show the current page with a green underline and `aria-current`. Icons are SVG, not emoji. Focus rings use `--primary`.

## Color theme

Keep the existing ResearchLanka tokens. Do not switch the admin area to the generic slate-and-status-green dashboard palette from the design-system search (`#1E293B` / `#22C55E` on a dark card). That palette is a different product. Consistency here means one token set, used the same way on every admin surface, in both themes.

| Issue | Where it shows | Change |
| --- | --- | --- |
| Light and dark brand hues differ | Light primary is forest green `#287c58`. Dark primary becomes cyan `#90d1d9`. | Design the dark admin theme as a darker forest green, not a new hue. Check text on `--surface`, `--sunk`, and `--wash` at 4.5:1. |
| Same job, different number color | Overview queue cards print counts in `--primary`. `StatTile` and AI-review `Metric` print counts in `--ink`. | One KPI treatment: label in `--muted`, figure in `--ink`, green only for the active nav item and the primary action. |
| AI work and resolution work look the same | AI review cards and resolution cards both use a green left border. The violet `--machine` token is reserved for generated content and is not used on the AI review queue. | Green left border = needs a human decision. Violet left border or “AI” label = model output. Warning / good / critical stay for flag and health states, always with a text label, never color alone. |
| Active controls use two themes | Admin section tabs use a green underline. AI-review view chips invert to ink-on-surface (`ViewLink`). | One active treatment: green text, green border or underline, `--primary-muted` fill. |
| Surfaces are not a scale | Header strip is `--sunk`. Tab bar is a mix of sunk and surface. Panels are `--surface`. Status banners use `--wash`. | Three named levels only: page (`--page`), card (`--surface`), recessed (`--sunk` or `--wash`). Do not invent a fourth mix for the tab bar. |

## Cards

One card component, used everywhere a figure or a work item appears.

Shared rules, aligned with a data-dense dashboard (12px radius already in `.panel`, 12px padding, 8px grid gap):

- Padding `p-3` (12px) on KPI tiles and `p-4` (16px) on work cards. Drop the mix of `p-4` and `p-5`.
- Label: `label-caps` in `--muted`. Value: one type size (`text-h2`), `--ink`, tabular numbers.
- Optional left bar only for status, using the semantic colors above, plus the status word.
- Hover and focus on clickable cards only (`QueueCard` already does this). Static metric tiles should not look clickable.
- Section spacing: one stack gap (`gap-6`) on Overview, Pipeline, AI review, Resolution, Flags, and Accounts. Overview currently uses `gap-8`; AI review uses `gap-4`.

Current card types that should collapse into that pattern:

- `StatTile` on Overview, Pipeline, and Accounts
- Local `QueueCard` on Overview (four cards in a three-column grid, so Accounts sits alone)
- Local `Metric` and `ReviewerSummary` on AI review
- `FlagCard`, `AIReviewCard`, and `ResolutionCard` (header, meta line, and action row differ in padding and border)

Queue cards should be a 2×2 grid from the `sm` breakpoint, or a single row of four from `lg`, so the last card is not stranded.

## Sidebar and horizontal panel

Both are needed. They must not list the same destinations.

UI/UX Pro Max treats a sidebar as the large-screen primary nav and a top or horizontal bar as the small-screen and in-page bar. Mixing a tab strip and a sidebar at the same level hides where you are. ResearchLanka already has both structures, but they are split the wrong way:

- The left `SiteNav` (240px) has a single “Administration” link. It stays one item for Overview, Pipeline, AI review, Resolution, Flags, and Accounts.
- Those six destinations live only in the horizontal `AdminNav` tab bar inside the content column.
- AI review then adds two more horizontal link rows (Queue / Reviewers, and My pending / Completed / All) that repeat the filter dropdowns.

Use them like this:

**Sidebar (section navigation).** Under the existing Admin group, list Overview, Pipeline, AI review, Resolution queue, Flag triage, and Accounts, each with its SVG icon and a text label. Highlight the current page with the same rail marker the public nav already uses (`nav-item[aria-current]`). Show a count badge only when the queue is non-zero. On viewports under 768px the rail already hides, so these links must also remain reachable.

**Horizontal panel (page context, not a second menu).** Keep one bar under the page title for the current screen only:

- Overview: API status, last load time, and the signed-in role.
- AI review: Queue versus Reviewers, then My pending / Completed / All. Remove the duplicate chip row that repeats the same choices as the filter form.
- Other pages: filters and the primary action, not another copy of the six sections.

The layout currently passes `badges={{ flags: 0, review: 0, aiReview: 0 }}`, so the tab chips never show real queue counts. When the sidebar and the horizontal panel are wired, those counts should be the live pending totals.

Do not add a third pattern (bottom nav) on desktop. On small screens, the horizontal panel is the admin section switcher because the sidebar is collapsed. From `lg` up, the sidebar owns section switching and the horizontal panel owns only the current page’s views and status.

## Other UX improvements

Priority follows the UI/UX Pro Max order: accessibility, then interaction, then navigation and feedback.

1. **One page heading.** The shell eyebrow “Administration” is a paragraph, and every page starts at `h2`. Give each admin route one `h1` (Overview, Pipeline, AI review, and so on). Keep section titles as `h2`.
2. **Say what is live.** The operations pattern asks for an update time and a stale state whenever a figure is labeled live. The API status line and the incremental-update panel should show “Updated at …” and a stale or unreachable state. The status dot already has text beside it; keep that.
3. **One primary action per screen.** Pipeline run, flag triage, and AI review decisions should keep a single filled green button. Destructive choices (reject, suspend) stay on `--danger` and sit apart from that button.
4. **Touch size.** Filter and date fields should be at least 44px tall, matching the AI-review search field (`min-h-11`). Tab links should meet that height too.
5. **Keyboard and focus.** Sidebar links, horizontal tabs, and view chips need the existing focus ring and a tab order that follows the visual order: skip link, sidebar, horizontal panel, then main content. Do not add scroll-reveal animation; the skill’s motion snippet does not belong on an operations console, and `prefers-reduced-motion` is already the right default.
6. **Deep links.** AI review filters already use the URL. Keep that. In-page tab changes should not jump scroll to the top (`scroll={false}` on those links).
7. **Empty and error states.** Keep the existing empty copy and API error panels. A failed monitoring or pipeline read should offer a retry, not only a static sentence.

## Suggested order of work

1. Token pass: dark primary stays forest green; one active-state style; one KPI number color.
2. Card pass: shared KPI tile and shared work card; fix the four-up queue grid.
3. Navigation pass: admin destinations in the sidebar; horizontal panel limited to page status and local views; live queue badges.
4. Heading, timestamps, and 44px controls.

No code was changed for this review.
