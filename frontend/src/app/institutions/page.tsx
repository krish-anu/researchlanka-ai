import { Suspense } from "react";

import { PageIntro } from "@/components/layout/PageIntro";
import { InstitutionAccessibilityPanel } from "@/components/analytics/ResearchPanels";
import { AnalyticsFilters, toFilterChoices, withoutQueryKey } from "@/components/analytics/AnalyticsFilters";
import {
  CompareCheckbox,
  InstitutionCompareProvider,
  ScopedInstitutionBars,
} from "@/components/institutions/CompareTray";
import { SearchBox } from "@/components/search/SearchBox";
import { ChartPanel, ChartSkeleton } from "@/components/ui/ChartPanel";
import { ChartExportMenu } from "@/components/ui/ChartExportMenu";
import { InsightsDisclosure } from "@/components/ui/InsightsDisclosure";
import {
  ApiErrorPanel,
  EmptyState,
  SectionHeading,
  emptyListState,
} from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { PrintMeta } from "@/components/ui/PrintMeta";
import {
  analyticsExportUrl,
  listInstitutions,
  getAnalyticsFields,
} from "@/services/api";
import { countActiveFilters, extractFilters, extractMinCount, extractPage, extractPageSize, PAGE_SIZE_OPTIONS, type SearchParams } from "@/services/filters";
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
  const minCount = extractMinCount(params);
  const page = extractPage(params);
  const pageSize = extractPageSize(params, 15);
  const query = typeof params.q === "string" ? params.q : "";
  const [result, fields] = await Promise.all([
    listInstitutions({
      ...filters,
      ...(minCount ? { min_count: minCount } : {}),
      page,
      page_size: pageSize,
    }),
    getAnalyticsFields({
      ...withoutQueryKey(withoutQueryKey(filters, "field"), "q"),
      limit: 100,
    }),
  ]);

  const chartEntries = result.ok
    ? result.value.data.slice(0, 15).map((entry) => ({
        label: entry.label,
        value: entry.publication_count,
      }))
    : [];

  return (
    <div className="flex flex-col gap-4">
      <PrintMeta
        title="Institutions"
        snapshotDate={result.ok ? result.value.meta.snapshot_date : null}
        searchParams={params}
      />
      <PageIntro
        title="Institutions"
        description="Sri Lankan institutions ranked by AI publication count. Open a row for the profile, or tick Compare on up to three."
      />
      <div className={countActiveFilters(params) === 0 ? "sticky top-14 z-20" : undefined}>
      <AnalyticsFilters
        params={params}
        basePath="/institutions"
        fields={toFilterChoices(fields.ok ? fields.value.data : [])}
        showMinCount
      />
      </div>

      <div className="max-w-4xl">
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
        <EmptyState {...emptyListState("institutions", "/institutions", filters)} />
      ) : (
        <InstitutionCompareProvider>
          <section>
            <SectionHeading
              title="All institutions"
              description={
                query
                  ? `${formatNumber(result.value.pagination.total)} ${
                      result.value.pagination.total === 1
                        ? "institution"
                        : "institutions"
                    } matching ${query}. Tick Compare on up to three rows.`
                  : "Ranked by publication count. Tick Compare on up to three rows."
              }
            />
            <div className="panel p-1">
              <RankingTable
                fitWidth
                entries={result.value.data}
                labelHeader="Institution"
                href={institutionHref}
                rankOffset={
                  (result.value.pagination.page - 1) *
                  result.value.pagination.page_size
                }
                leadingColumn={{
                  header: "Compare",
                  render: (row) => <CompareCheckbox label={row.label} />,
                }}
              />
            </div>
            <div className="mt-3">
              <Pagination
                pagination={result.value.pagination}
                basePath="/institutions"
                searchParams={params}
                pageSizes={PAGE_SIZE_OPTIONS}
              />
            </div>
          </section>

          <InsightsDisclosure
            title="Insights"
            description="Leading institutions on this page."
          >
            <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
              <ChartPanel
                title="AI publication output by institution"
                description={
                  chartEntries[0]
                    ? `${chartEntries[0].label} leads this page with ${chartEntries[0].value.toLocaleString("en-GB")} publications.`
                    : "Leading institutions on this page."
                }
                action={
                  <ChartExportMenu
                    csvHref={analyticsExportUrl("institutions", filters)}
                  />
                }
              >
                <ScopedInstitutionBars
                  entries={chartEntries.map((entry) => ({
                    ...entry,
                    href: institutionHref(entry.label),
                  }))}
                />
              </ChartPanel>
              <Suspense
                fallback={
                  <ChartSkeleton label="Loading institution accessibility…" />
                }
              >
                <InstitutionAccessibilityPanel
                  filters={filters}
                  entries={result.value.data}
                  scopeToCompare
                />
              </Suspense>
            </div>
          </InsightsDisclosure>

          <SnapshotNote
            snapshotDate={result.value.meta.snapshot_date}
            datasetStage={result.value.meta.dataset_stage}
          />
        </InstitutionCompareProvider>
      )}
    </div>
  );
}
