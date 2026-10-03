import { PageIntro } from "@/components/layout/PageIntro";
import { FilterDrawer } from "@/components/publications/FilterDrawer";
import {
  ActiveFilters,
  FilterControls,
  PublicationSort,
} from "@/components/publications/FilterControls";
import { PublicationCardList } from "@/components/publications/PublicationCard";
import { SearchBox } from "@/components/search/SearchBox";
import { DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState, emptyListState } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { SnapshotNote } from "@/components/ui/Provenance";
import { PrintMeta } from "@/components/ui/PrintMeta";
import { exportUrl, listPublications } from "@/services/api";
import {
  countActiveFilters,
  extractFilters,
  extractPage,
  extractSort,
  type SearchParams,
} from "@/services/filters";
import { formatNumber } from "@/services/format";

export const metadata = {
  title: "AI publications",
  description:
    "Explore Sri Lankan research publications across disciplines, institutions, and research areas.",
};

/**
 * Results-first directory: search + toolbar + list. Corpus KPIs live on the
 * overview — repeating them here competed with scanning titles.
 */
export default async function PublicationsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const page = extractPage(params);
  const sort = extractSort(params);
  const query = typeof params.q === "string" ? params.q : "";

  const result = await listPublications({
    ...filters,
    page,
    page_size: 25,
    sort,
    include_facets: true,
  });

  return (
    <div className="flex flex-col gap-4">
      <PrintMeta
        title="AI publications"
        snapshotDate={result.ok ? result.value.meta.snapshot_date : null}
        searchParams={params}
        extra={
          result.ok && result.value.meta.dataset_stage
            ? [`Stage: ${result.value.meta.dataset_stage}`]
            : undefined
        }
      />
      <PageIntro title="Publications" />

      <SearchBox
        initialQuery={query}
        targetPath="/publications"
        label="Search publications"
        placeholder="Search publications by title, author, DOI…"
        suggestionTypes={["publication", "journal"]}
      />

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="publication results" />
      ) : (
        <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[auto_minmax(0,1fr)] lg:gap-5">
          <div className="lg:sticky lg:top-16 lg:max-h-[calc(100vh-5rem)] lg:self-start lg:overflow-y-auto">
            <FilterDrawer activeCount={countActiveFilters(params)} collapsible>
              <FilterControls
                searchParams={params}
                facets={result.value.facets}
              />
            </FilterDrawer>
          </div>

          <section className="flex min-w-0 flex-col gap-4">
            <ActiveFilters searchParams={params} />

            {result.value.data.length === 0 ? (
              <>
                <div>
                  <h2 className="font-display text-h2 text-ink">Publications</h2>
                  <p className="text-body-sm text-ink-secondary">
                    <span className="font-medium text-ink">0</span> results
                  </p>
                </div>
                <EmptyState
                  {...emptyListState("publications", "/publications", filters)}
                />
              </>
            ) : (
              <>
                <PublicationCardList
                  publications={result.value.data}
                  initialView="cards"
                  layout="row"
                  toolbar={
                    <div className="flex flex-wrap items-end justify-between gap-2">
                      <div>
                        <h2 className="font-display text-h2 text-ink">Publications</h2>
                        <p
                          className="text-body-sm text-ink-secondary"
                          role="status"
                          aria-live="polite"
                        >
                          <span className="font-medium text-ink">
                            {formatNumber(result.value.pagination.total)}
                          </span>{" "}
                          {result.value.pagination.total === 1 ? "result" : "results"}
                          {query ? (
                            <>
                              {" "}
                              matching{" "}
                              <span className="font-medium text-ink">{query}</span>
                            </>
                          ) : null}
                        </p>
                      </div>
                      <div className="flex gap-2">
                        <DownloadLink href={exportUrl("publications.csv", filters)}>
                          CSV
                        </DownloadLink>
                        <DownloadLink href={exportUrl("publications.jsonl", filters)}>
                          JSONL
                        </DownloadLink>
                      </div>
                    </div>
                  }
                  controls={<PublicationSort searchParams={params} />}
                />
                <Pagination
                  pagination={result.value.pagination}
                  basePath="/publications"
                  searchParams={params}
                />
              </>
            )}

            <SnapshotNote
              snapshotDate={result.value.meta.snapshot_date}
              datasetStage={result.value.meta.dataset_stage}
              includeDate={false}
            />
          </section>
        </div>
      )}
    </div>
  );
}
