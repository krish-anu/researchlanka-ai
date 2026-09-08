import Link from "next/link";
import { notFound } from "next/navigation";

import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { CollaborationNetwork } from "@/components/network/CollaborationNetwork";
import { NetworkSummaryPanel } from "@/components/network/NetworkMetrics";
import { PublicationCardList } from "@/components/publications/PublicationCard";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { SnapshotNote } from "@/components/ui/Provenance";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import {
  exportUrl,
  getCollaborationNetwork,
  getInstitution,
  getInstitutionCollaborators,
  getInstitutionPublications,
  isNotFound,
} from "@/services/api";
import { topValues, yearHistogram } from "@/services/derive";
import { extractPage, type SearchParams } from "@/services/filters";
import {
  formatCompact,
  formatDecimal,
  formatNumber,
  formatRatioAsPercent,
  formatYearRange,
} from "@/services/format";
import {
  decodeKeySegments,
  institutionHref,
  publicationSearchHref,
} from "@/services/links";

interface PageProps {
  params: Promise<{ key: string[] }>;
  searchParams: Promise<SearchParams>;
}

export async function generateMetadata({ params }: PageProps) {
  const { key } = await params;
  const name = decodeKeySegments(key);
  return {
    title: name,
    description: `Research output, citation totals, collaborators and publications for ${name}.`,
  };
}

const PAGE_SIZE = 25;
const TREND_SAMPLE = 100;
const TREND_YEAR_MIN = 2016;
const TREND_YEAR_MAX = new Date().getFullYear();

export default async function InstitutionProfilePage({
  params,
  searchParams,
}: PageProps) {
  const { key } = await params;
  const query = await searchParams;
  const institutionKey = decodeKeySegments(key);
  const page = extractPage(query);

  const profile = await getInstitution(institutionKey);
  if (isNotFound(profile)) notFound();
  if (!profile.ok) {
    return <ApiErrorPanel error={profile.error} what="this institution profile" />;
  }

  const data = profile.value.data;

  const [publications, collaborators, trendSample, network] = await Promise.all([
    getInstitutionPublications(institutionKey, { page, page_size: PAGE_SIZE }),
    getInstitutionCollaborators(institutionKey, { limit: 25 }),
    getInstitutionPublications(institutionKey, {
      page: 1,
      page_size: TREND_SAMPLE,
      year_min: TREND_YEAR_MIN,
      year_max: TREND_YEAR_MAX,
    }),
    getCollaborationNetwork({
      scope: "institution",
      institution: [data.label],
      limit: 40,
      min_weight: 1,
    }),
  ]);

  const sample = trendSample.ok ? trendSample.value.data : [];
  const sampleTotal = trendSample.ok ? trendSample.value.pagination.total : 0;
  const trend = yearHistogram(sample);
  const isTruncated = sampleTotal > TREND_SAMPLE;
  const openAccessShare =
    sample.length > 0
      ? sample.filter((item) => item.is_oa).length / sample.length
      : null;
  const topFields = topValues(sample, (item) => [item.primary_field], 10);

  return (
    <div className="flex flex-col gap-5">
      <nav className="text-body-sm text-muted">
        <Link href="/institutions" className="hover:text-ink hover:underline">
          Institutions
        </Link>
        <span aria-hidden> / </span>
        <span>{data.label}</span>
      </nav>

      <header className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="font-display text-h1 text-ink">{data.label}</h1>
          <p className="mt-1 text-body-sm text-ink-secondary">
            Records span {formatYearRange(data.year_min, data.year_max)}
          </p>
        </div>
        <Link
          href={`/institutions/compare?institution=${encodeURIComponent(data.label)}`}
          className="shrink-0 rounded-md border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
        >
          Compare with another →
        </Link>
      </header>

      <StatTileGrid>
        <StatTile
          label="Publications"
          value={formatCompact(data.publication_count)}
          caption="records with this affiliation"
        />
        <StatTile
          label="Citations"
          value={formatCompact(data.citation_total)}
          caption={`${formatDecimal(data.average_citations)} per publication`}
        />
        <StatTile
          label="Open access"
          value={
            openAccessShare === null ? "—" : formatRatioAsPercent(openAccessShare)
          }
          caption={
            isTruncated
              ? `share within the ${TREND_SAMPLE}-record sample`
              : "share of this institution's records"
          }
        />
        <StatTile
          label="Partner institutions"
          value={
            collaborators.ok
              ? formatNumber(collaborators.value.data.length)
              : "—"
          }
          caption="co-publishing partners (top 25 shown)"
        />
      </StatTileGrid>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartPanel
          title="Publications per year"
          description={
            isTruncated
              ? `Derived from the ${TREND_SAMPLE} most recent of ${formatNumber(sampleTotal)} records — not the full history.`
              : "Derived from this institution's full publication list."
          }
          table={
            trend.length > 0 ? (
              <TableDisclosure>
                <DataTable
                  columns={[
                    { key: "year", header: "Year", render: (row) => String(row.key) },
                    {
                      key: "count",
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
                  ]}
                  rows={trend}
                  rowKey={(row) => String(row.key)}
                />
              </TableDisclosure>
            ) : null
          }
        >
          {trend.length > 0 ? (
            <TrendLineChart
              points={trend.map((bucket) => ({
                key: bucket.key,
                value: bucket.publication_count,
              }))}
              valueLabel="Publications"
              ariaLabel={`Publications per year for ${data.label}`}
              height={240}
            />
          ) : (
            <p className="p-4 text-body-sm text-muted">
              No records with a publication year.
            </p>
          )}
        </ChartPanel>

        <section className="panel p-4">
          <SectionHeading
            title="Collaborating institutions"
            description="Institutions appearing alongside this one on shared publications."
          />
          {!collaborators.ok ? (
            <ApiErrorPanel error={collaborators.error} what="collaborators" />
          ) : collaborators.value.data.length === 0 ? (
            <p className="p-4 text-body-sm text-muted">
              No co-publishing partners recorded.
            </p>
          ) : (
            <DataTable
              columns={[
                {
                  key: "institution",
                  header: "Institution",
                  render: (row) => (
                    <Link
                      href={institutionHref(row.institution)}
                      className="hover:underline"
                    >
                      {row.institution}
                    </Link>
                  ),
                },
                {
                  key: "count",
                  header: "Shared publications",
                  numeric: true,
                  render: (row) => formatNumber(row.publication_count),
                },
              ]}
              rows={collaborators.value.data}
              rowKey={(row) => row.institution}
            />
          )}
        </section>
      </div>

      {network.ok && network.value.data.nodes.length > 0 ? (
        <ChartPanel
          title="Collaboration network"
          description="Co-publishing structure around this institution."
        >
          <div className="flex flex-col gap-5">
            <CollaborationNetwork
              network={network.value.data}
              scope="institution"
              height={380}
            />
            <NetworkSummaryPanel summary={network.value.data.summary} />
          </div>
        </ChartPanel>
      ) : null}

      {topFields.length > 0 ? (
        <section className="panel p-4">
          <SectionHeading
            title="Research fields"
            description="Fields most represented across the sampled publication list."
          />
          <ul className="flex flex-wrap gap-2">
            {topFields.map((entry) => (
              <li key={entry.label}>
                <Link
                  href={publicationSearchHref({
                    field: entry.label,
                    institution: data.label,
                  })}
                  className="inline-flex items-center gap-1.5 rounded-full border border-rule px-2.5 py-1 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
                >
                  {entry.label}
                  <span className="data-mono text-muted">{entry.count}</span>
                </Link>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-body-sm text-muted">
            Department and faculty breakdowns are not available: the consolidated
            dataset records institution-level affiliations only, with no
            sub-unit field to group by.
          </p>
        </section>
      ) : null}

      <section>
        <SectionHeading
          title="Publications"
          description="Every record affiliated with this institution, newest first."
          action={
            <DownloadLink
              href={exportUrl("publications.csv", { institution: [data.label] })}
            >
              Export list (CSV)
            </DownloadLink>
          }
        />
        {!publications.ok ? (
          <ApiErrorPanel error={publications.error} what="publications" />
        ) : publications.value.data.length === 0 ? (
          <EmptyState title="No publications found for this institution" />
        ) : (
          <div className="flex flex-col gap-4">
            <PublicationCardList publications={publications.value.data} />
            <Pagination
              pagination={publications.value.pagination}
              basePath={institutionHref(institutionKey)}
              searchParams={query}
            />
          </div>
        )}
      </section>

      <SnapshotNote
        snapshotDate={profile.value.meta.snapshot_date}
        datasetStage={profile.value.meta.dataset_stage}
      />
    </div>
  );
}
