import Link from "next/link";
import { Suspense, type ReactNode } from "react";
import { AnalyticsFilters } from "@/components/analytics/AnalyticsFilters";
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
import { ChartPanel, ChartSkeleton, DownloadLink } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, PanelSkeleton } from "@/components/ui/Feedback";
import { SnapshotNote } from "@/components/ui/Provenance";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { Button } from "@/components/ui/Button";
import {
  analyticsExportUrl,
  buildQuery,
  getAnalyticsFields,
  getAnalyticsInstitutions,
  getAnalyticsOverview,
  getPublicationYearCoverage,
  listPublications,
  type QueryParams,
} from "@/services/api";
import { clampYearFilters, extractFilters, type SearchParams } from "@/services/filters";
import { formatCompact, formatNumber, formatRatioAsPercent } from "@/services/format";
import { institutionHref, publicationHref } from "@/services/links";

export const metadata = {
  title: "AI research overview",
  description:
    "Publication trends, institutions, fields, and collaborations within Sri Lanka’s accepted AI research collection.",
};

function StorySection({
  title,
  description,
  children,
}: {
  title: string;
  description: string;
  children: ReactNode;
}) {
  return (
    <section className="overview-story">
      <header className="mb-4">
        <h2 className="font-display text-h2 text-ink">{title}</h2>
        <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
          {description}
        </p>
      </header>
      {children}
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
  const [overview, fields, institutions, filterFields] = await Promise.all([
    getAnalyticsOverview(filters),
    getAnalyticsFields({ ...filters, limit: 100 }),
    getAnalyticsInstitutions({ ...filters, limit: 12 }),
    getAnalyticsFields({ ...filters, field: undefined, limit: 100 }),
  ]);
  const entries = fields.ok ? fields.value.data : [];

  return (
    <div className="flex flex-col gap-8">
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

      <div className="overview-controls">
        <AnalyticsFilters
          params={params}
          fields={
            filterFields.ok
              ? filterFields.value.data.map((entry) => entry.label)
              : entries.map((entry) => entry.label)
          }
          defaultFrom={coverage?.start}
          defaultTo={coverage?.end}
        />
        <ActiveFilters searchParams={params} basePath="/" />
      </div>

      {!overview.ok ? (
        <ApiErrorPanel error={overview.error} what="AI research metrics" />
      ) : (
        <section aria-label="AI collection metrics">
          <StatTileGrid>
            <StatTile
              label="AI publications"
              icon={<PublicationsIcon />}
              value={formatCompact(overview.value.data.publication_count)}
              caption="accepted AI records in this selection"
            />
            <StatTile
              label="Institutions"
              icon={<InstitutionsIcon />}
              value={
                institutions.ok
                  ? formatNumber(institutions.value.pagination.total)
                  : "—"
              }
              caption="with AI publications in this selection"
            />
            <StatTile
              label="Open access"
              icon={<OpenAccessIcon />}
              value={formatRatioAsPercent(overview.value.data.open_access_share)}
              caption="share of selected AI publications"
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
            className="mt-3"
          />
        </section>
      )}

      <StorySection
        title="How AI output is changing"
        description="Annual publication trends and the share of work across research fields in the current selection."
      >
        <div className="analytics-grid">
          <Suspense
            fallback={<ChartSkeleton label="Loading AI research output…" />}
          >
            <TrendPanel filters={filters} />
          </Suspense>
          {fields.ok ? (
            <FieldDistributionPanel
              entries={entries}
              filters={filters}
              total={
                overview.ok ? overview.value.data.publication_count : undefined
              }
            />
          ) : (
            <ApiErrorPanel error={fields.error} what="research fields" />
          )}
        </div>
      </StorySection>

      <StorySection
        title="Where research concentrates"
        description="Leading institutions by AI publication count, and how field activity shifts over recent years."
      >
        <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
          <ChartPanel
            title="Institutions advancing AI research"
            description="Leading institutions by AI publication count."
            action={
              <DownloadLink href={analyticsExportUrl("institutions", filters)} />
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
                }))}
                valueLabel="AI publications"
                ariaLabel="Leading institutions by AI publication count"
              />
            ) : (
              <ApiErrorPanel
                error={institutions.error}
                what="institution rankings"
              />
            )}
            <Link
              href={`/institutions${buildQuery(filters)}`}
              className="mt-4 inline-block text-xs text-primary hover:underline"
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
        description="Institutional collaboration links in the current selection — shared publications as edges."
      >
        <Suspense
          fallback={
            <ChartSkeleton label="Loading collaboration network…" size="xl" />
          }
        >
          <NetworkPanel filters={filters} />
        </Suspense>
      </StorySection>

      <StorySection
        title="Recent publications"
        description="A sample of the newest AI-related records matching the filters above."
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
  return (
    <ChartPanel
      title="A closer look at AI research"
      description="Recent publications in the current selection."
      action={
        <Link
          href={`/publications${buildQuery(filters)}`}
          className="text-xs text-primary hover:underline"
        >
          Browse AI publications →
        </Link>
      }
    >
      <DataTable
        rows={result.value.data}
        rowKey={(row) => row.publication_key}
        columns={[
          {
            key: "title",
            header: "Publication",
            render: (row) => (
              <div>
                <Link
                  href={publicationHref(row.publication_key)}
                  className="font-medium text-ink hover:text-primary"
                >
                  {row.title ?? "Untitled record"}
                </Link>
                <p className="mt-1 text-xs text-muted">
                  {row.authors.slice(0, 3).join(", ")}
                </p>
              </div>
            ),
          },
          {
            key: "field",
            header: "Field",
            render: (row) => row.primary_field ?? "Unclassified",
          },
          {
            key: "year",
            header: "Year",
            numeric: true,
            render: (row) => row.publication_year ?? "—",
          },
          {
            key: "access",
            header: "Access",
            render: (row) =>
              row.is_oa ? (
                <span className="rounded bg-primary-muted px-2 py-1 text-xs text-primary">
                  Open access
                </span>
              ) : (
                "Not marked open"
              ),
          },
        ]}
      />
    </ChartPanel>
  );
}
