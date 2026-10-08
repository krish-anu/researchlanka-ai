import Link from "next/link";
import { AnalyticsFilters, toFilterChoices, withoutQueryKey } from "@/components/analytics/AnalyticsFilters";
import { ResearcherLandscape } from "@/components/analytics/ResearcherLandscape";
import { PageIntro } from "@/components/layout/PageIntro";
import { ActiveFilters } from "@/components/publications/FilterControls";
import { FilterDrawer } from "@/components/publications/FilterDrawer";
import { SearchBox } from "@/components/search/SearchBox";
import { ApiErrorPanel, EmptyState, emptyListState } from "@/components/ui/Feedback";
import { InsightsDisclosure } from "@/components/ui/InsightsDisclosure";
import { Pagination } from "@/components/ui/Pagination";
import { PrintMeta } from "@/components/ui/PrintMeta";
import { SnapshotNote } from "@/components/ui/Provenance";
import {
  getAnalyticsFields,
  getAnalyticsInstitutions,
  getClaimedNameProfiles,
  listResearchers,
} from "@/services/api";
import {
  countActiveFilters,
  extractFilters,
  extractMaxCount,
  extractMinCount,
  extractPage,
  type SearchParams,
} from "@/services/filters";
import { formatNumber, formatYearRange, personName } from "@/services/format";
import { authorProfileHref, researcherHref } from "@/services/links";

function directoryQuery(params: SearchParams): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (key === "page") continue;
    const items = Array.isArray(value) ? value : value ? [value] : [];
    for (const item of items) search.append(key, item);
  }
  return search.toString();
}

export const metadata = {
  title: "Researchers",
  description:
    "Explore researchers through their publication activity, research areas, and institutional affiliations.",
};

export default async function ResearchersPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const minCount = extractMinCount(params);
  const maxCount = extractMaxCount(params);
  const page = extractPage(params);
  const query = typeof params.q === "string" ? params.q : "";
  const [result, fields, institutions] = await Promise.all([
    listResearchers({
      ...filters,
      ...(minCount ? { min_count: minCount } : {}),
      ...(maxCount ? { max_count: maxCount } : {}),
      page,
      page_size: 25,
    }),
    getAnalyticsFields({
      ...withoutQueryKey(withoutQueryKey(filters, "field"), "q"),
      limit: 100,
    }),
    getAnalyticsInstitutions({
      ...withoutQueryKey(withoutQueryKey(filters, "institution"), "q"),
      limit: 100,
    }),
  ]);

  // Spellings a verified author has claimed point at their one profile, so a
  // person listed here under several names can be recognised as one.
  const claimed =
    result.ok && result.value.data.length > 0
      ? await getClaimedNameProfiles(result.value.data.map((entry) => entry.label))
      : null;
  const claimedNames = claimed?.ok ? claimed.value.data : {};

  return (
    <div className="flex flex-col gap-4">
      <PrintMeta
        title="Researchers"
        snapshotDate={result.ok ? result.value.meta.snapshot_date : null}
        searchParams={params}
      />
      <PageIntro title="Researchers" />

      <SearchBox
        initialQuery={query}
        targetPath="/researchers"
        label="Search researchers"
        placeholder="Search researchers..."
      />

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="the researcher directory" />
      ) : (
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[15.5rem_minmax(0,1fr)] lg:gap-6">
          <div className="lg:sticky lg:top-16 lg:self-start">
            <FilterDrawer
              activeCount={countActiveFilters(params) + (minCount || maxCount ? 1 : 0)}
              label="Refine researchers"
            >
              <AnalyticsFilters
                params={params}
                basePath="/researchers"
                fields={toFilterChoices(fields.ok ? fields.value.data : [])}
                institutions={toFilterChoices(
                  institutions.ok ? institutions.value.data : [],
                )}
                yearPhrase="Publication years"
                fromLabel="From"
                toLabel="To"
                showMinCount
                layout="refine"
              />
            </FilterDrawer>
          </div>

          <section className="flex min-w-0 flex-col gap-3">
            <ActiveFilters searchParams={params} basePath="/researchers" />
            {result.value.data.length === 0 ? (
              <EmptyState {...emptyListState("researchers", "/researchers", filters)} />
            ) : (
              <>
                <div>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <h2 className="font-display text-h2 text-ink">Researchers</h2>
                    <p className="text-body-sm text-ink-secondary" role="status" aria-live="polite">
                      <span className="font-medium text-ink">
                        {formatNumber(result.value.pagination.total)}
                      </span>{" "}
                      {result.value.pagination.total === 1 ? "researcher" : "researchers"}
                      {query ? (
                        <>
                          {" "}
                          matching <span className="font-medium text-ink">{query}</span>
                        </>
                      ) : null}
                    </p>
                  </div>
                  <p className="text-body-sm text-muted">
                    Ordered by publication count. Entries are grouped by display name, so the same name can combine different people.
                  </p>
                </div>
                <div>
                  <div className="researcher-columns" aria-hidden="true">
                    <span>Researcher</span>
                    <span>Research area</span>
                    <span>Publications</span>
                  </div>
                  <ol className="researcher-results">
                    {result.value.data.map((entry, index) => {
                      const years = formatYearRange(entry.year_min, entry.year_max);
                      const yearLabel = years === "—" ? "" : years;
                      return (
                        <li key={`${entry.key}-${index}`} className="researcher-row">
                          <div className="min-w-0">
                            <Link href={researcherHref(entry.label)} className="researcher-name">
                              {personName(entry.label)}
                              <span className="researcher-open">View researcher →</span>
                            </Link>
                            {entry.affiliation ? (
                              <p className="researcher-affiliation">{entry.affiliation}</p>
                            ) : null}
                            {claimedNames[entry.label] ? (
                              <Link
                                href={authorProfileHref(claimedNames[entry.label].slug)}
                                className="mt-0.5 inline-flex items-center gap-1 text-body-sm text-success-text hover:underline"
                              >
                                <span aria-hidden>✓</span> Verified: {claimedNames[entry.label].display_name}
                              </Link>
                            ) : null}
                          </div>
                          {entry.areas?.length ? (
                            <p className="researcher-areas">{entry.areas.join(" · ")}</p>
                          ) : (
                            <span aria-hidden="true" />
                          )}
                          <p className="researcher-metrics">
                            <span className="researcher-count">
                              {formatNumber(entry.publication_count)}
                            </span>
                            <span className="researcher-count-label">
                              {entry.publication_count === 1 ? "publication" : "publications"}
                            </span>
                            {yearLabel ? (
                              <span className="researcher-years">{yearLabel}</span>
                            ) : null}
                          </p>
                        </li>
                      );
                    })}
                  </ol>
                </div>
                <Pagination
                  pagination={result.value.pagination}
                  basePath="/researchers"
                  searchParams={params}
                />
                <InsightsDisclosure
                  title="Researcher landscape"
                  description="Researchers by institution and by publication count in this selection."
                >
                  <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
                    <ResearcherLandscape queryString={directoryQuery(params)} />
                  </div>
                </InsightsDisclosure>
                <SnapshotNote
                  snapshotDate={result.value.meta.snapshot_date}
                  datasetStage={result.value.meta.dataset_stage}
                />
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
