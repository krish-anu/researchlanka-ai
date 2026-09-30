# UI change log

Changes made against the ResearchLanka screens, kept on the existing forest, paper, and turmeric tokens. Chart zoom that can walk off the data is limited. Filters that used to refresh the page on the first control now wait until the reader commits them.

## Search

- Suggestion loading uses a small spinner in the field and soft shimmer rows in the menu. The previous search navigation cue was a 2px bar across the page; it is now a compact “Updating results” status.
- The top search field and Search button sit in one shell. The button is no longer drawn over the text.
- The field is a normal text input, so the browser’s search decorations are not shown.
- Suggestions are balanced across publications, journals, researchers, and institutions, so an institution match is not crowded out by titles.
- Tab fills the highlighted completion. On the institutions directory, choosing an institution fills the search and filters that list.

## Overview

- Changing “Year from” or “Year to” no longer reloads the overview. The page reloads when a research field is chosen, or when “All fields” is chosen. Year values already in the form go with that choice.
- “All fields” is the first option in the research-field list.
- “AI research output over time” draws the open-access series on the same line chart. Zoom in, zoom out, and reset stay available. The axes cannot move outside the years and counts on the chart, and the wheel does not zoom.
- The landscape mosaic fills more of its card. The Mosaic and Counts controls are shorter. Opening a field scales the next mosaic into place over about half a second.
- “Where AI research is growing” no longer zooms. Drag, scroll, and the zoom tools are off, so the heatmap stays on the fields and years it was drawn for.
- Chart and Table controls are shorter, so they no longer read as an empty row above a chart. The same applies to the recent-publications panel chrome.

## AI publications

- “Relevance” is offered only when a search query is present. Without a query it is not sent, including from Apply.
- Apply waits for publication type, institution, and journal. Those three are select boxes. They no longer navigate on each click.
- The refine control that said “Narrow” is an up triangle while the panel is open and a down triangle when it is collapsed.
- The numbers on each publication row are the publication year and the citation count, not a list index. They stay, with the word “cites” beside the citation count.

## Publication record

- Author names are initials. Hover or keyboard focus shows the name and institution. When the record has one institution per author, that institution is the one shown; otherwise the record’s institutions are shown together.
- The abstract card is only as wide as the text measure, instead of a full-width card with text on one side.
- The reference count sits with the reference list at the end of the page. If no list was captured, the section states the count and says so.
- A back control returns to the previous page, so the list filters in that history entry remain.

## Topics and researchers

- Topics spacing is tighter so the mosaic sits higher on the page.
- The mosaic drill uses the same slower expand as the overview.
- “All publication counts” is the placeholder on the minimum-count field. Any whole number of 1 or more is accepted. Anything else is rejected in the form and is not submitted.
- Researcher names are title case on the directory, the profile title, and the co-author list.
- The profile title and metrics scroll away. Only the section tabs stay pinned, so cards are not covered by a tall sticky header.
- The publications-per-year chart no longer stretches to the height of the co-author list. The co-author list scrolls inside its own panel.

## Institutions

- “AI publication output by institution” and “Output & accessibility” chart the compared institutions when at least one is ticked. With none ticked, they chart the current page.
- The institution checklist under the bar chart is removed.
- When no filter is selected, the filter card stays pinned while the directory scrolls.
- Page length can be 10, 15, 20, 25, or 50. The default is 15.
- Both institution charts keep fixed axes. Zoom controls are removed, matching the growing-fields heatmap.
- Institution search suggests names and Tab fills them. Choosing a suggestion filters the directory.

## Admin

- The AI update reads the from date, to date, and review threshold whether the request uses snake_case or camelCase, and stores that window on the run status. The form rejects a from date after the to date, and a threshold outside 0–1, before it starts a run.
- AI review cards use the same forest primary and paper surface as the rest of the product.
- Resolution-queue DOIs, and DOIs on AI review cards, open `https://doi.org/…`.
- The pipeline page uses the same tighter card spacing as the other admin screens, and the update form states which records the threshold keeps in review.
