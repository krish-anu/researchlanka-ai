import { Suspense } from "react";
import { PageIntro } from "@/components/layout/PageIntro";
import { InstitutionAccessibilityPanel } from "@/components/analytics/ResearchPanels";
import { AnalyticsFilters } from "@/components/analytics/AnalyticsFilters";
import Link from "next/link";

import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { SearchBox } from "@/components/search/SearchBox";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState, SectionHeading, Skeleton } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { analyticsExportUrl, listInstitutions, getAnalyticsFields } from "@/services/api";
import { extractFilters, extractPage, type SearchParams } from "@/services/filters";
import { formatNumber } from "@/services/format";
import { institutionHref } from "@/services/links";

export const metadata = {
  title: "Institutions",
  description:
    "Sri Lankan research institutions ranked by publication output, with profiles and head-to-head comparison.",
};

export default async function InstitutionsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const page = extractPage(params);
  const query = typeof params.q === "string" ? params.q : "";
  const [result, fields] = await Promise.all([listInstitutions({ ...filters, page, page_size: 25 }), getAnalyticsFields({ limit: 100 })]);

  return (
    <div className="flex flex-col gap-4">
      <PageIntro title="Places where AI ideas grow." description="Compare institutional AI research output, accessibility, and partnerships." action={<Link href="/institutions/compare" className="button">Compare institutions →</Link>} />
      <AnalyticsFilters params={params} basePath="/institutions" fields={fields.ok ? fields.value.data.map(f => f.label) : []} />

      <div className="max-w-2xl">
        <SearchBox
          initialQuery={query}
          targetPath="/institutions"
          label="Search institutions"
          placeholder="Search institution names..."
        />
      </div>

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="the institution directory" />
      ) : result.value.data.length === 0 ? (
        <EmptyState
          title={query ? "No institutions match this search" : "No institutions found"}
          description={
            query
              ? "Try a broader institution name or search the publications directory."
              : "No institution aggregates matched the current filters."
          }
        />
      ) : (
        <>
          <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2"><ChartPanel
            title="AI publication output by institution"
            description="Leading 15 institutions on this directory page."
            action={<DownloadLink href={analyticsExportUrl("institutions", filters)} />}
          >
            <RankingBarChart
              entries={result.value.data.slice(0, 15).map((entry) => ({
                label: entry.label,
                value: entry.publication_count,
              }))}
              valueLabel="Publications"
              ariaLabel="Bar chart of publications by institution"
            />
          </ChartPanel><Suspense fallback={<Skeleton className="h-96" />}><InstitutionAccessibilityPanel filters={filters} entries={result.value.data} /></Suspense></div>

          <section>
            <SectionHeading
              title="All institutions"
              description={
                query
                  ? `${formatNumber(result.value.pagination.total)} ${
                      result.value.pagination.total === 1
                        ? "institution"
                        : "institutions"
                    } matching ${query}.`
                  : "Ranked by publication count."
              }
            />
            <div className="panel p-1">
              <RankingTable
                entries={result.value.data}
                labelHeader="Institution"
                href={institutionHref}
                rankOffset={
                  (result.value.pagination.page - 1) *
                  result.value.pagination.page_size
                }
              />
            </div>
            <div className="mt-3">
              <Pagination
                pagination={result.value.pagination}
                basePath="/institutions"
                searchParams={params}
              />
            </div>
          </section>

          <SnapshotNote
            snapshotDate={result.value.meta.snapshot_date}
            datasetStage={result.value.meta.dataset_stage}
          />
        </>
      )}
    </div>
  );
}
