import { PageIntro } from "@/components/layout/PageIntro";
import { DataQualityIcon, InstitutionsIcon, OpenAccessIcon, PublicationsIcon } from "@/components/layout/NavIcons";
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
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { exportUrl, getAnalyticsInstitutions, getAnalyticsOverview, listPublications } from "@/services/api";
import {
  extractFilters,
  extractPage,
  extractSort,
  type SearchParams,
} from "@/services/filters";
import { formatNumber, formatRatioAsPercent } from "@/services/format";

export const metadata = {
  title: "AI publications",
  description:
    "Search accepted Sri Lankan AI publications by year, type, institution, field, topic, journal, and data quality.",
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

  const [result, overview, institutions] = await Promise.all([
    listPublications({ ...filters, page, page_size: 25, sort, include_facets: true }),
    getAnalyticsOverview(filters),
    getAnalyticsInstitutions({ ...filters, limit: 1 }),
  ]);

  return (
    <div className="flex flex-col gap-4">
      <PageIntro title="Discover AI research." description="Search AI-related titles, abstracts, authors, journals, and DOIs. Refine by field, source, access, or metadata quality." />

      {result.ok && overview.ok ? <StatTileGrid>
        <StatTile label="AI publications" icon={<PublicationsIcon />} value={formatNumber(result.value.pagination.total)} caption="Accepted AI records in this selection" />
        <StatTile label="Institutions" icon={<InstitutionsIcon />} value={institutions.ok ? formatNumber(institutions.value.pagination.total) : "—"} caption="With AI-related publications" />
        <StatTile label="Open access" icon={<OpenAccessIcon />} value={formatRatioAsPercent(overview.value.data.open_access_share)} caption="Share of selected AI publications" />
        <StatTile label="DOI coverage" icon={<DataQualityIcon />} value={formatRatioAsPercent(overview.value.data.doi_coverage)} caption="Records with a DOI" />
      </StatTileGrid> : null}

      <div className="max-w-2xl">
        <SearchBox initialQuery={query} />
      </div>

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="publication results" />
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-[16rem_minmax(0,1fr)]">
          <aside className="flex flex-col gap-3">
            <FilterControls searchParams={params} />
            {result.value.facets ? (
              <FacetPanel facets={result.value.facets} searchParams={params} />
            ) : null}
          </aside>

          <section className="flex min-w-0 flex-col gap-4">
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-body-sm text-ink-secondary">
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
                <PublicationCardList publications={result.value.data} initialView="table" />
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
