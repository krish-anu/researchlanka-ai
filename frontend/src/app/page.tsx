import Link from "next/link";
import { Suspense, type ReactNode } from "react";
import { AnalyticsFilters, toFilterChoices, withoutQueryKey } from "@/components/analytics/AnalyticsFilters";
import {
  ActivityPanel,
  FieldDistributionPanel,
  NetworkPanel,
  TrendPanel,
} from "@/components/analytics/ResearchPanels";
import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { OverviewHero } from "@/components/layout/PageIntro";
import {
  DataQualityIcon,
  InstitutionsIcon,
  OpenAccessIcon,
  PublicationsIcon,
} from "@/components/layout/NavIcons";
import { ActiveFilters } from "@/components/publications/FilterControls";
import { PublicationCardList } from "@/components/publications/PublicationCard";
import { ChartPanel, ChartSkeleton, NestedChartTitles } from "@/components/ui/ChartPanel";
import { ChartExportMenu } from "@/components/ui/ChartExportMenu";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, EmptyState, PanelSkeleton } from "@/components/ui/Feedback";
import { PrintMeta } from "@/components/ui/PrintMeta";
import { SnapshotNote, formatSnapshotDate } from "@/components/ui/Provenance";
import { StickyChrome } from "@/components/ui/StickyChrome";
import { StatTile, StatTileGrid, TrendSparkline } from "@/components/ui/StatTile";
import { Button } from "@/components/ui/Button";
import {
  analyticsExportUrl,
  buildQuery,
  getAnalyticsFields,
  getAnalyticsInstitutions,
  getAnalyticsOverview,
  getAnalyticsTrends,
  getPublicationYearCoverage,
  listPublications,
  type QueryParams,
} from "@/services/api";
import {
  CAPTION,
  filtersNarrowSelection,
  withSelectionScope,
} from "@/services/copy";
import { clampYearFilters, extractFilters, type SearchParams } from "@/services/filters";
import { formatCompact, formatNumber, formatRatioAsPercent } from "@/services/format";
import { institutionHref } from "@/services/links";

export const metadata = {
  title: "AI research overview",
  description:
    "Publication trends, institutions, fields, and collaborations within Sri Lanka’s accepted AI collection.",
};

function StorySection({
  id,
  title,
  children,
}: {
  id?: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="overview-story">
      <header className="mb-3">
        <h2 className="font-display text-h2 text-ink">{title}</h2>
      </header>
      <NestedChartTitles>{children}</NestedChartTitles>
    </section>
  );
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const coverage = await getPublicationYearCoverage();
  const filters = clampYearFilters(
    {
      ...(coverage ? { year_min: coverage.start, year_max: coverage.end } : {}),
      ...extractFilters(params),
    },
    coverage,
  );
  const [overview, fields, institutions, filterFields, trends] = await Promise.all([
    getAnalyticsOverview(filters),
    getAnalyticsFields({ ...filters, limit: 100 }),
    getAnalyticsInstitutions({ ...filters, limit: 12 }),
    getAnalyticsFields({ ...withoutQueryKey(filters, "field"), limit: 100 }),
    getAnalyticsTrends({ ...filters, group_by: "year" }),
  ]);
  const entries = fields.ok ? fields.value.data : [];
  const selectionScoped = filtersNarrowSelection(filters);
  const sparkValues = trends.ok
    ? [...trends.value.data]
        .sort((a, b) => Number(a.key) - Number(b.key))
        .map((point) => point.publication_count)
    : [];
  const asOf = overview.ok
    ? formatSnapshotDate(overview.value.meta.snapshot_date)
    : null;

  return (
    <div className="flex flex-col gap-4">
      <PrintMeta
        title="AI research overview"
        snapshotDate={overview.ok ? overview.value.meta.snapshot_date : null}
        searchParams={params}
        extra={
          overview.ok && overview.value.meta.dataset_stage
            ? [`Stage: ${overview.value.meta.dataset_stage}`]
            : undefined
        }
      />
      <OverviewHero
        action={
          <Button
            href={analyticsExportUrl("overview", filters)}
            variant="secondary"
            size="sm"
            className="research-hero-cta"
          >
            Export overview
          </Button>
        }
      />

      <StickyChrome className="overview-controls-wrap" stickyClassName="overview-controls">
        <AnalyticsFilters
          params={params}
          fields={toFilterChoices(
            filterFields.ok ? filterFields.value.data : entries,
          )}
          defaultFrom={coverage?.start}
          defaultTo={coverage?.end}
          deferUntilField
        />
        <ActiveFilters searchParams={params} basePath="/" />
      </StickyChrome>

      {!overview.ok ? (
        <ApiErrorPanel error={overview.error} what="AI research metrics" />
      ) : (
        <section aria-label="AI collection metrics">
          <StatTileGrid asOf={asOf}>
            <StatTile
              label="AI publications"
              icon={<PublicationsIcon />}
              value={formatCompact(overview.value.data.publication_count)}
              caption={CAPTION.recordsInSelection}
              spark={
                <TrendSparkline
                  values={sparkValues}
                  href="#ai-output-trends"
                  label="Publications over time — jump to trend chart"
                />
              }
            />
            <StatTile
              label="Institutions"
              icon={<InstitutionsIcon />}
              value={
                institutions.ok
                  ? formatNumber(institutions.value.pagination.total)
                  : "—"
              }
              caption={CAPTION.institutionsInSelection}
            />
            <StatTile
              label="Open access"
              icon={<OpenAccessIcon />}
              value={formatRatioAsPercent(overview.value.data.open_access_share)}
              caption={CAPTION.shareOfSelected}
            />
            <StatTile
              label="DOI coverage"
              icon={<DataQualityIcon />}
              value={formatRatioAsPercent(overview.value.data.doi_coverage)}
              caption={`Abstract coverage ${formatRatioAsPercent(overview.value.data.abstract_coverage)}`}
              hint={`From ${overview.value.data.source_count} source datasets`}
            />
          </StatTileGrid>
          <SnapshotNote
            snapshotDate={overview.value.meta.snapshot_date}
            datasetStage={overview.value.meta.dataset_stage}
            includeDate={false}
            className="mt-3"
          />
        </section>
      )}

      <StorySection
        id="ai-output-trends"
        title="How AI output is changing"
      >
        <div className="analytics-grid">
          <Suspense
            fallback={<ChartSkeleton label="Loading AI research output…" />}
          >
            <TrendPanel filters={filters} />
          </Suspense>
          <Suspense
            fallback={<ChartSkeleton label="Loading field distribution…" />}
          >
            {fields.ok ? (
              <FieldDistributionPanel
                entries={entries}
                filters={filters}
                total={
                  overview.ok
                    ? overview.value.data.publication_count
                    : undefined
                }
              />
            ) : (
              <ApiErrorPanel error={fields.error} what="research fields" />
            )}
          </Suspense>
        </div>
      </StorySection>

      <StorySection
        title="Where research concentrates"
      >
        <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
          <ChartPanel
            title="Institutions advancing AI research"
            description={withSelectionScope(
              "Institutions ranked by AI publication count",
              selectionScoped,
            )}
            action={
              <ChartExportMenu
                csvHref={analyticsExportUrl("institutions", filters)}
              />
            }
            table={
              institutions.ok ? (
                <TableDisclosure>
                  <DataTable
                    rows={institutions.value.data}
                    rowKey={(row) => row.key}
                    columns={[
                      {
                        key: "name",
                        header: "Institution",
                        render: (row) => (
                          <Link
                            href={institutionHref(row.label)}
                            className="hover:underline"
                          >
                            {row.label}
                          </Link>
                        ),
                      },
                      {
                        key: "count",
                        header: "AI publications",
                        numeric: true,
                        render: (row) => formatNumber(row.publication_count),
                      },
                    ]}
                  />
                </TableDisclosure>
              ) : null
            }
          >
            {institutions.ok ? (
              <RankingBarChart
                entries={institutions.value.data.map((row) => ({
                  label: row.label,
                  value: row.publication_count,
                  href: institutionHref(row.label),
                }))}
                valueLabel="AI publications"
                ariaLabel="Leading institutions by AI publication count"
                clearHref={selectionScoped ? "/" : undefined}
              />
            ) : (
              <ApiErrorPanel
                error={institutions.error}
                what="institution rankings"
              />
            )}
            <Link
              href={`/institutions${buildQuery(filters)}`}
              className="mt-3 inline-block text-body-sm text-primary hover:underline"
            >
              Browse institutions →
            </Link>
          </ChartPanel>
          <Suspense
            fallback={<ChartSkeleton label="Loading field activity…" size="lg" />}
          >
            <ActivityPanel
              filters={filters}
              fields={entries.map((entry) => entry.label)}
            />
          </Suspense>
        </div>
      </StorySection>

      <StorySection
        title="Who works with whom"
      >
        <Suspense
          fallback={
            <ChartSkeleton label="Loading collaboration network…" size="xl" />
          }
        >
          <NetworkPanel filters={filters} compact />
        </Suspense>
      </StorySection>

      <StorySection
        title="Recent publications"
      >
        <Suspense
          fallback={<PanelSkeleton label="Loading recent publications…" />}
        >
          <RecentPublications filters={filters} />
        </Suspense>
      </StorySection>
    </div>
  );
}

async function RecentPublications({ filters }: { filters: QueryParams }) {
  const result = await listPublications({
    ...filters,
    sort: "year_desc",
    page_size: 5,
  });
  if (!result.ok) {
    return <ApiErrorPanel error={result.error} what="recent publications" />;
  }
  const scoped = filtersNarrowSelection(filters);
  return (
    <ChartPanel
      title="A closer look at AI research"
      description={withSelectionScope(
        "Newest matching publications",
        scoped,
      )}
      action={
        <Link
          href={`/publications${buildQuery(filters)}`}
          className="text-body-sm text-primary hover:underline"
        >
          Browse AI publications →
        </Link>
      }
    >
      {result.value.data.length === 0 ? (
        <EmptyState
          bare
          title="No publications match the current filters"
          description={
            scoped
              ? "Try removing a year or field filter to widen the results."
              : undefined
          }
          recovery={scoped ? { kind: "clear-filters", href: "/" } : undefined}
        />
      ) : (
        <PublicationCardList
          publications={result.value.data}
          initialView="cards"
        />
      )}
    </ChartPanel>
  );
}
