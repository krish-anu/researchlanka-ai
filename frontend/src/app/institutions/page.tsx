import Link from "next/link";

import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { analyticsExportUrl, listInstitutions } from "@/services/api";
import { extractFilters, extractPage, type SearchParams } from "@/services/filters";
import { institutionHref } from "@/services/links";

export const metadata = {
  title: "Institutions",
  description:
    "Sri Lankan research institutions ranked by publication output and citations, with profiles and head-to-head comparison.",
};

export default async function InstitutionsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const page = extractPage(params);
  const result = await listInstitutions({ ...filters, page, page_size: 25 });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-h1 text-ink">Institutions</h1>
          <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
            Research output by institution, drawn from affiliations recorded on
            each publication.
          </p>
        </div>
        <Link
          href="/institutions/compare"
          className="shrink-0 rounded-md border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
        >
          Compare institutions →
        </Link>
      </div>

      {!result.ok ? (
        <ApiErrorPanel error={result.error} what="the institution directory" />
      ) : result.value.data.length === 0 ? (
        <EmptyState
          title="No institutions found"
          description="No institution aggregates matched the current filters."
        />
      ) : (
        <>
          <ChartPanel
            title="Publication output by institution"
            description="Top 15 institutions by number of records."
            action={<DownloadLink href={analyticsExportUrl("institutions")} />}
          >
            <RankingBarChart
              entries={result.value.data.slice(0, 15).map((entry) => ({
                label: entry.label,
                value: entry.publication_count,
              }))}
              valueLabel="Publications"
              ariaLabel="Bar chart of publications by institution"
            />
          </ChartPanel>

          <section>
            <SectionHeading
              title="All institutions"
              description="Ranked by publication count."
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
