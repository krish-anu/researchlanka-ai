import { ApiErrorPanel, EmptyState } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { SearchBox } from "@/components/search/SearchBox";
import { listResearchers } from "@/services/api";
import { extractFilters, extractPage, type SearchParams } from "@/services/filters";
import { formatNumber } from "@/services/format";
import { researcherHref } from "@/services/links";

export const metadata = {
  title: "Researchers",
  description:
    "Most active authors in the Sri Lankan research corpus, ranked by number of publications recorded.",
};

export default async function ResearchersPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const page = extractPage(params);
  const query = typeof params.q === "string" ? params.q : "";
  const result = await listResearchers({ ...filters, page, page_size: 25 });

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="font-display text-h1 text-ink">Researchers</h1>
        <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
          Author aggregates ranked by publication count. Open a profile for the
          full publication list, co-author network, and output over time.
        </p>
      </div>

      <div className="max-w-2xl">
        <SearchBox
          initialQuery={query}
          targetPath="/researchers"
          label="Search researchers"
          placeholder="Search researcher names..."
        />
      </div>

      <div className="panel border-warning/40 p-3">
        <p className="flex gap-2 text-body-sm text-ink-secondary">
          <span aria-hidden className="text-warning">
            ▲
          </span>
          <span>
            <strong className="font-medium text-ink">
              Author names are not disambiguated.
            </strong>{" "}
            Profiles group records by normalised display name, so common names
            may merge distinct people and name variants may split one person
            across several entries. Treat these aggregates as indicative.
          </span>
        </p>
      </div>

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="the researcher directory" />
      ) : result.value.data.length === 0 ? (
        <EmptyState
          title={query ? "No researchers match this search" : "No researchers found"}
          description={
            query
              ? "Try a broader name spelling or search the publications directory."
              : "No author aggregates matched the current filters."
          }
        />
      ) : (
        <>
          <p className="text-body-sm text-ink-secondary">
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
          <div className="panel p-1">
            <RankingTable
              entries={result.value.data}
              labelHeader="Researcher"
              href={researcherHref}
              rankOffset={
                (result.value.pagination.page - 1) *
                result.value.pagination.page_size
              }
            />
          </div>
          <Pagination
            pagination={result.value.pagination}
            basePath="/researchers"
            searchParams={params}
          />
          <SnapshotNote
            snapshotDate={result.value.meta.snapshot_date}
            datasetStage={result.value.meta.dataset_stage}
          />
        </>
      )}
    </div>
  );
}
