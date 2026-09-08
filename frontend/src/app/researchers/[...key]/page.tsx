import Link from "next/link";
import { notFound } from "next/navigation";

import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { CollaborationNetwork } from "@/components/network/CollaborationNetwork";
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
  getResearcher,
  getResearcherCoauthors,
  getResearcherPublications,
  isNotFound,
} from "@/services/api";
import { topValues, yearHistogram } from "@/services/derive";
import { extractPage, type SearchParams } from "@/services/filters";
import {
  formatCompact,
  formatDecimal,
  formatNumber,
  formatYearRange,
} from "@/services/format";
import {
  decodeKeySegments,
  publicationSearchHref,
  researcherHref,
  topicHref,
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
    description: `Publication record, co-authors and research output over time for ${name}.`,
  };
}

const PAGE_SIZE = 25;
/** Max page size the API allows; the trend is derived from this window. */
const TREND_SAMPLE = 100;
const TREND_YEAR_MIN = 2016;
const TREND_YEAR_MAX = new Date().getFullYear();

export default async function ResearcherProfilePage({
  params,
  searchParams,
}: PageProps) {
  const { key } = await params;
  const query = await searchParams;
  const researcherKey = decodeKeySegments(key);
  const page = extractPage(query);

  const profile = await getResearcher(researcherKey);
  if (isNotFound(profile)) notFound();
  if (!profile.ok) {
    return <ApiErrorPanel error={profile.error} what="this researcher profile" />;
  }

  const data = profile.value.data;
  const [publications, coauthors, trendSample, network] = await Promise.all([
    getResearcherPublications(researcherKey, { page, page_size: PAGE_SIZE }),
    getResearcherCoauthors(researcherKey, { limit: 25 }),
    getResearcherPublications(researcherKey, {
      page: 1,
      page_size: TREND_SAMPLE,
      year_min: TREND_YEAR_MIN,
      year_max: TREND_YEAR_MAX,
    }),
    getCollaborationNetwork({
      scope: "researcher",
      researcher: [data.label],
      limit: 40,
      min_weight: 1,
    }),
  ]);

  const sample = trendSample.ok ? trendSample.value.data : [];
  const sampleTotal = trendSample.ok ? trendSample.value.pagination.total : 0;
  const trend = yearHistogram(sample);
  const isTruncated = sampleTotal > TREND_SAMPLE;
  const topFields = topValues(sample, (item) => [item.primary_field]);

  return (
    <div className="flex flex-col gap-5">
      <nav className="text-body-sm text-muted">
        <Link href="/researchers" className="hover:text-ink hover:underline">
          Researchers
        </Link>
        <span aria-hidden> / </span>
        <span>{data.label}</span>
      </nav>

      <header>
        <h1 className="font-display text-h1 text-ink">{data.label}</h1>
        <p className="mt-1 text-body-sm text-ink-secondary">
          Active {formatYearRange(data.year_min, data.year_max)}
        </p>
      </header>

      <div className="panel border-warning/40 p-3">
        <p className="flex gap-2 text-body-sm text-ink-secondary">
          <span aria-hidden className="text-warning">
            ▲
          </span>
          <span>
            This profile is grouped by{" "}
            <strong className="font-medium text-ink">
              {data.disambiguation_level === "name"
                ? "normalised author name"
                : data.disambiguation_level}
            </strong>
            , not a verified identifier. Records from different people sharing
            this name may be combined here.{" "}
            <Link
              href="/data-quality"
              className="text-primary hover:underline"
            >
              How to read these figures
            </Link>
          </span>
        </p>
      </div>

      <StatTileGrid>
        <StatTile
          label="Publications"
          value={formatCompact(data.publication_count)}
          caption="records attributed to this name"
        />
        <StatTile
          label="Citations"
          value={formatCompact(data.citation_total)}
          caption={`${formatDecimal(data.average_citations)} per publication`}
        />
        <StatTile
          label="Active years"
          value={formatYearRange(data.year_min, data.year_max)}
          caption="first to most recent record"
        />
        <StatTile
          label="Co-authors"
          value={
            coauthors.ok ? formatNumber(coauthors.value.data.length) : "—"
          }
          caption="distinct collaborators (top 25 shown)"
        />
      </StatTileGrid>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ChartPanel
          title="Publications per year"
          description={
            isTruncated
              ? `Derived from the ${TREND_SAMPLE} most recent of ${formatNumber(sampleTotal)} records — not the full history.`
              : "Derived from this researcher's full publication list."
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
            title="Co-authors"
            description="Most frequent collaborators on shared publications."
          />
          {!coauthors.ok ? (
            <ApiErrorPanel error={coauthors.error} what="co-authors" />
          ) : coauthors.value.data.length === 0 ? (
            <p className="p-4 text-body-sm text-muted">
              No co-authors recorded for this researcher.
            </p>
          ) : (
            <DataTable
              columns={[
                {
                  key: "name",
                  header: "Co-author",
                  render: (row) => (
                    <Link
                      href={researcherHref(row.name)}
                      className="hover:underline"
                    >
                      {row.name}
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
              rows={coauthors.value.data}
              rowKey={(row) => row.name}
            />
          )}
        </section>
      </div>

      {topFields.length > 0 ? (
        <section className="panel p-4">
          <SectionHeading
            title="Publishes in"
            description="Fields most represented across the sampled publication list."
          />
          <ul className="flex flex-wrap gap-2">
            {topFields.map((entry) => (
              <li key={entry.label}>
                <Link
                  href={publicationSearchHref({ field: entry.label })}
                  className="inline-flex items-center gap-1.5 rounded-full border border-rule px-2.5 py-1 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
                >
                  {entry.label}
                  <span className="data-mono text-muted">
                    {entry.count}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <ChartPanel
        title="Author collaboration network"
        description="Co-author links across publications attributed to this researcher."
      >
        {!network.ok ? (
          <ApiErrorPanel error={network.error} what="the author collaboration network" />
        ) : (
          <CollaborationNetwork
            network={network.value.data}
            scope="researcher"
            height={380}
          />
        )}
      </ChartPanel>

      <section>
        <SectionHeading
          title="Publications"
          description="Every record attributed to this name, newest first."
          action={
            <DownloadLink href={exportUrl("publications.csv", { q: data.label })}>
              Export list (CSV)
            </DownloadLink>
          }
        />
        {!publications.ok ? (
          <ApiErrorPanel error={publications.error} what="publications" />
        ) : publications.value.data.length === 0 ? (
          <EmptyState title="No publications found for this researcher" />
        ) : (
          <div className="flex flex-col gap-4">
            <PublicationCardList publications={publications.value.data} />
            <Pagination
              pagination={publications.value.pagination}
              basePath={researcherHref(researcherKey)}
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
