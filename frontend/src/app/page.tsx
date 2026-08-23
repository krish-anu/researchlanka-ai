import Link from "next/link";
import { Suspense } from "react";

import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { CollaborationNetwork } from "@/components/network/CollaborationNetwork";
import {
  NetworkBrokersTable,
  NetworkSummaryPanel,
} from "@/components/network/NetworkMetrics";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure, type Column } from "@/components/ui/DataTable";
import { ApiErrorPanel, Skeleton } from "@/components/ui/Feedback";
import { SnapshotNote } from "@/components/ui/Provenance";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import {
  analyticsExportUrl,
  getAnalyticsFields,
  getAnalyticsInstitutions,
  getAnalyticsOverview,
  getAnalyticsTrends,
  getCollaborationNetwork,
} from "@/services/api";
import {
  formatCompact,
  formatDecimal,
  formatNumber,
  formatRatioAsPercent,
} from "@/services/format";
import { institutionHref, publicationSearchHref } from "@/services/links";
import type { RankingEntry, TrendPoint } from "@/types/api";

export const metadata = {
  title: "National research dashboard",
  description:
    "Publication and citation trends, institutional output, research fields, and collaboration structure across the Sri Lankan research corpus.",
};

/** Trends group by year; sort numerically so the x-axis reads chronologically. */
function sortByYear(points: TrendPoint[]): TrendPoint[] {
  return [...points].sort((a, b) => Number(a.key) - Number(b.key));
}

const rankingColumns = (
  labelHeader: string,
  href?: (label: string) => string,
): Column<RankingEntry>[] => [
  {
    key: "label",
    header: labelHeader,
    render: (row) =>
      href ? (
        <Link href={href(row.label)} className="hover:underline">
          {row.label}
        </Link>
      ) : (
        row.label
      ),
  },
  {
    key: "publications",
    header: "Publications",
    numeric: true,
    render: (row) => formatNumber(row.publication_count),
  },
  {
    key: "citations",
    header: "Citations",
    numeric: true,
    render: (row) => formatNumber(row.citation_total),
  },
];

/* ------------------------------------------------------------------ page */

/**
 * The analytics endpoints aggregate in Python over the whole corpus, so the
 * slow panels stream behind their own Suspense boundaries rather than holding
 * up the headline figures.
 *
 * Streaming is opened *inside* the page rather than via a `loading.tsx`: a
 * segment-level loading file would also wrap every nested route, flushing
 * headers before a detail route could call `notFound()` and costing correct
 * 404 statuses.
 */
export default async function DashboardPage() {
  const overview = await getAnalyticsOverview();

  return (
    <div className="flex flex-col gap-6">
      <PageIntro />

      {!overview.ok ? (
        <ApiErrorPanel error={overview.error} what="the national dashboard" />
      ) : (
        <section aria-labelledby="headline">
          <h2 id="headline" className="sr-only">
            Headline metrics
          </h2>
          <StatTileGrid>
            <StatTile
              label="Publications"
              value={formatCompact(overview.value.data.publication_count)}
              caption="records in the consolidated dataset"
            />
            <StatTile
              label="Citations"
              value={formatCompact(overview.value.data.citation_total)}
              caption={`${formatDecimal(overview.value.data.average_citations)} per publication on average`}
            />
            <StatTile
              label="Open access"
              value={formatRatioAsPercent(overview.value.data.open_access_share)}
              caption="of records flagged open access"
            />
            <StatTile
              label="DOI coverage"
              value={formatRatioAsPercent(overview.value.data.doi_coverage)}
              caption={`abstract coverage ${formatRatioAsPercent(overview.value.data.abstract_coverage)}`}
              hint={`Drawn from ${overview.value.data.source_count} source dataset${
                overview.value.data.source_count === 1 ? "" : "s"
              }`}
            />
          </StatTileGrid>
          <SnapshotNote
            snapshotDate={overview.value.meta.snapshot_date}
            datasetStage={overview.value.meta.dataset_stage}
            className="mt-2"
          />
        </section>
      )}

      <Suspense fallback={<PanelPairSkeleton />}>
        <TrendsSection />
      </Suspense>

      <Suspense fallback={<PanelPairSkeleton />}>
        <RankingsSection />
      </Suspense>

      <Suspense fallback={<Skeleton className="h-[30rem]" />}>
        <NetworkSection />
      </Suspense>
    </div>
  );
}

/* -------------------------------------------------------------- sections */

async function TrendsSection() {
  const trends = await getAnalyticsTrends({ group_by: "year" });
  const points = trends.ok ? sortByYear(trends.value.data) : [];

  const yearTable = (
    valueKey: "publication_count" | "citation_total",
    header: string,
  ) => (
    <TableDisclosure>
      <DataTable
        columns={[
          { key: "year", header: "Year", render: (row) => String(row.key) },
          {
            key: "value",
            header,
            numeric: true,
            render: (row) => formatNumber(row[valueKey]),
          },
        ]}
        rows={points}
        rowKey={(row) => String(row.key)}
      />
    </TableDisclosure>
  );

  // Publications and citations differ by orders of magnitude, so they are two
  // charts on two axes rather than one chart with a second y-scale.
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <ChartPanel
        title="Publications per year"
        description="Records with a recorded publication year."
        action={<DownloadLink href={analyticsExportUrl("trends")} />}
        table={points.length > 0 ? yearTable("publication_count", "Publications") : null}
      >
        {!trends.ok ? (
          <ApiErrorPanel error={trends.error} what="publication trends" />
        ) : points.length === 0 ? (
          <p className="p-4 text-body-sm text-muted">No trend data available.</p>
        ) : (
          <TrendLineChart
            points={points.map((point) => ({
              key: point.key,
              value: point.publication_count,
            }))}
            valueLabel="Publications"
            ariaLabel="Line chart of publications per year"
          />
        )}
      </ChartPanel>

      <ChartPanel
        title="Citations per year"
        description="Citations accruing to publications of each year; recent years are still accumulating."
        table={points.length > 0 ? yearTable("citation_total", "Citations") : null}
      >
        {points.length > 0 ? (
          <TrendLineChart
            points={points.map((point) => ({
              key: point.key,
              value: point.citation_total,
            }))}
            valueLabel="Citations"
            ariaLabel="Line chart of citations per publication year"
          />
        ) : (
          <p className="p-4 text-body-sm text-muted">No citation trend available.</p>
        )}
      </ChartPanel>
    </div>
  );
}

async function RankingsSection() {
  const [institutions, fields] = await Promise.all([
    getAnalyticsInstitutions({ limit: 12 }),
    getAnalyticsFields({ limit: 12 }),
  ]);

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <ChartPanel
        title="Most active institutions"
        description="Sri Lankan institutions by number of publications recorded."
        action={<DownloadLink href={analyticsExportUrl("institutions")} />}
        table={
          institutions.ok ? (
            <TableDisclosure>
              <DataTable
                columns={rankingColumns("Institution", institutionHref)}
                rows={institutions.value.data}
                rowKey={(row, index) => `${row.key}-${index}`}
              />
            </TableDisclosure>
          ) : null
        }
      >
        {!institutions.ok ? (
          <ApiErrorPanel error={institutions.error} what="institution rankings" />
        ) : institutions.value.data.length === 0 ? (
          <p className="p-4 text-body-sm text-muted">No institution data available.</p>
        ) : (
          <RankingBarChart
            entries={institutions.value.data.map((entry) => ({
              label: entry.label,
              value: entry.publication_count,
            }))}
            valueLabel="Publications"
            ariaLabel="Bar chart of publications by institution"
          />
        )}
      </ChartPanel>

      <ChartPanel
        title="Research fields"
        description="Publications by primary field. Under-represented fields are the short bars."
        action={<DownloadLink href={analyticsExportUrl("fields")} />}
        table={
          fields.ok ? (
            <TableDisclosure>
              <DataTable
                columns={rankingColumns("Field", (label) =>
                  publicationSearchHref({ field: label }),
                )}
                rows={fields.value.data}
                rowKey={(row, index) => `${row.key}-${index}`}
              />
            </TableDisclosure>
          ) : null
        }
      >
        {!fields.ok ? (
          <ApiErrorPanel error={fields.error} what="the field breakdown" />
        ) : fields.value.data.length === 0 ? (
          <p className="p-4 text-body-sm text-muted">No field data available.</p>
        ) : (
          <RankingBarChart
            entries={fields.value.data.map((entry) => ({
              label: entry.label,
              value: entry.publication_count,
            }))}
            valueLabel="Publications"
            ariaLabel="Bar chart of publications by research field"
          />
        )}
      </ChartPanel>
    </div>
  );
}

async function NetworkSection() {
  const network = await getCollaborationNetwork({
    scope: "institution",
    limit: 120,
    min_weight: 1,
  });

  return (
    <ChartPanel
      title="Institutional collaboration network"
      description="Institutions that co-publish in the national corpus."
      action={
        <Link href="/institutions" className="text-body-sm text-primary hover:underline">
          Browse institutions →
        </Link>
      }
      table={
        network.ok && network.value.data.edges.length > 0 ? (
          <TableDisclosure label="View collaboration pairs as table">
            <DataTable
              columns={[
                {
                  key: "source",
                  header: "Institution",
                  render: (row) => row.source_label ?? row.source,
                },
                {
                  key: "target",
                  header: "Collaborator",
                  render: (row) => row.target_label ?? row.target,
                },
                {
                  key: "weight",
                  header: "Shared publications",
                  numeric: true,
                  render: (row) => formatNumber(row.weight),
                },
              ]}
              rows={network.value.data.edges}
              rowKey={(row, index) => `${row.source}-${row.target}-${index}`}
            />
          </TableDisclosure>
        ) : null
      }
    >
      {!network.ok ? (
        <ApiErrorPanel error={network.error} what="the collaboration network" />
      ) : (
        <div className="flex flex-col gap-5">
          <CollaborationNetwork network={network.value.data} scope="institution" />
          <NetworkSummaryPanel summary={network.value.data.summary} />
          <div>
            <h3 className="mb-2 font-display text-h3 text-ink">
              Bridging institutions
            </h3>
            <p className="mb-3 max-w-prose text-body-sm text-ink-secondary">
              Institutions carrying the most shortest paths between others. A
              different ranking from the most prolific: an institution that only
              co-publishes inside its own cluster brokers nothing, however much
              it publishes.
            </p>
            <NetworkBrokersTable nodes={network.value.data.nodes} />
          </div>
        </div>
      )}
    </ChartPanel>
  );
}

/* ---------------------------------------------------------------- chrome */

function PanelPairSkeleton() {
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2" aria-busy="true">
      <Skeleton className="h-80" />
      <Skeleton className="h-80" />
    </div>
  );
}

function PageIntro() {
  return (
    <div>
      <h1 className="font-display text-h1 text-ink">
        Sri Lanka research at a glance
      </h1>
      <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
        A public, read-only view of the consolidated national publication
        corpus. Browse{" "}
        <Link href="/publications" className="text-primary hover:underline">
          publications
        </Link>
        ,{" "}
        <Link href="/researchers" className="text-primary hover:underline">
          researchers
        </Link>
        , and{" "}
        <Link href="/institutions" className="text-primary hover:underline">
          institutions
        </Link>
        , or review the{" "}
        <Link href="/data-quality" className="text-primary hover:underline">
          data quality notes
        </Link>{" "}
        behind these figures.
      </p>
    </div>
  );
}
