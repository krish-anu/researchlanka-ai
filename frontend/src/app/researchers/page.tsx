import { AnalyticsFilters } from "@/components/analytics/AnalyticsFilters";
import Link from "next/link";
import { ViewSwitcher } from "@/components/ui/ViewSwitcher";
import { PageIntro } from "@/components/layout/PageIntro";
import { ApiErrorPanel, EmptyState } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { SearchBox } from "@/components/search/SearchBox";
import { listResearchers, getAnalyticsFields } from "@/services/api";
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
  const [result, fields] = await Promise.all([listResearchers({ ...filters, page, page_size: 25 }), getAnalyticsFields({ limit: 100 })]);

  return (
    <div className="flex flex-col gap-4">
      <PageIntro title="People behind the progress." description="Discover researchers through their AI publications, co-author networks, and output over time." />

      <AnalyticsFilters params={params} basePath="/researchers" fields={fields.ok ? fields.value.data.map(f => f.label) : []} />
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
          <ViewSwitcher label="Researcher directory view" cards={<div className="directory-cards">{result.value.data.map((entry, index) => <article key={`${entry.key}-${index}`} className="panel p-5"><div className="mb-4 flex items-center justify-between"><span className="directory-avatar">{entry.label.split(/\s+/).slice(0,2).map(part => part[0]).join("")}</span><span className="text-xs text-muted">#{(result.value.pagination.page - 1) * result.value.pagination.page_size + index + 1}</span></div><h2 className="text-h3"><Link href={researcherHref(entry.label)} className="hover:text-primary">{entry.label}</Link></h2><div className="my-4 border-t border-rule pt-4"><strong className="text-2xl tabular">{formatNumber(entry.publication_count)}</strong><p className="mt-1 text-xs text-muted">AI-related publications</p></div><Link href={researcherHref(entry.label)} className="text-xs font-medium text-primary">Explore researcher →</Link></article>)}</div>} table={
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
          </div>          } />
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
