import { FacetPanel } from "@/components/publications/FacetPanel";
import {
  ActiveFilters,
  FilterControls,
} from "@/components/publications/FilterControls";
import { PublicationCardList } from "@/components/publications/PublicationCard";
import { SearchBox } from "@/components/search/SearchBox";
import { DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { SnapshotNote } from "@/components/ui/Provenance";
import { exportUrl, listPublications } from "@/services/api";
import {
  extractFilters,
  extractPage,
  extractSort,
  type SearchParams,
} from "@/services/filters";
import { formatNumber } from "@/services/format";

export const metadata = {
  title: "Publications",
  description:
    "Search and filter the consolidated Sri Lankan research publication corpus by year, type, institution, field, topic, journal, and data quality.",
};

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
      <div>
        <h1 className="text-2xl font-semibold text-ink">Publications</h1>
        <p className="mt-1 max-w-prose text-sm text-ink-secondary">
          Full-text search across titles, abstracts, authors, journals and DOIs,
          with structured filters. Every record carries its source provenance and
          any data-quality flags.
        </p>
      </div>

      <div className="lg:hidden">
        <SearchBox initialQuery={query} />
      </div>

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="publication results" />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]">
          <aside className="flex flex-col gap-3">
            <FilterControls searchParams={params} />
            {result.value.facets ? (
              <FacetPanel facets={result.value.facets} searchParams={params} />
            ) : null}
          </aside>

          <section className="flex min-w-0 flex-col gap-4">
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm text-ink-secondary">
                  <span className="font-medium text-ink">
                    {formatNumber(result.value.pagination.total)}
                  </span>{" "}
                  {result.value.pagination.total === 1 ? "record" : "records"}
                  {query ? (
                    <>
                      {" "}
                      matching <span className="font-medium text-ink">{query}</span>
                    </>
                  ) : null}
                </p>
                <div className="flex gap-2">
                  <DownloadLink href={exportUrl("publications.csv", filters)}>
                    CSV
                  </DownloadLink>
                  <DownloadLink href={exportUrl("publications.jsonl", filters)}>
                    JSONL
                  </DownloadLink>
                </div>
              </div>
              <ActiveFilters searchParams={params} />
            </div>

            {result.value.data.length === 0 ? (
              <EmptyState
                title="No publications match these filters"
                description="Try widening the year range, removing a filter, or searching for a broader term."
              />
            ) : (
              <>
                <PublicationCardList publications={result.value.data} />
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
            />
          </section>
        </div>
      )}
    </div>
  );
}
