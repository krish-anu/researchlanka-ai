import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { ProfileHeader, ProfileTabs } from "@/components/layout/ProfileHeader";
import { InstitutionNetworkPanel } from "@/components/network/ProfileNetworkPanels";
import { PublicationCardList } from "@/components/publications/PublicationCard";
import { ChartPanel, ChartSkeleton, DownloadLink } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { PrintMeta } from "@/components/ui/PrintMeta";
import { SnapshotNote } from "@/components/ui/Provenance";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import {
  exportUrl,
  getInstitution,
  getInstitutionCollaborators,
  getInstitutionPublications,
  isNotFound,
} from "@/services/api";
import { publicationsForDisplay, topValues, yearHistogram } from "@/services/derive";
import { extractPage, type SearchParams } from "@/services/filters";
import {
  formatCompact,
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
    description: `Research output, collaborators and publications for ${name}.`,
  };
}

const PAGE_SIZE = 25;
const TREND_SAMPLE = 100;

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

  const [publications, collaborators, trendSample] = await Promise.all([
    getInstitutionPublications(institutionKey, { page, page_size: PAGE_SIZE }),
    getInstitutionCollaborators(institutionKey, { limit: 25 }),
    getInstitutionPublications(institutionKey, {
      page: 1,
      page_size: TREND_SAMPLE,
    }),
  ]);

  const sample = trendSample.ok ? trendSample.value.data : [];
  const sampleTotal = trendSample.ok ? trendSample.value.pagination.total : 0;
  const isTruncated = sampleTotal > TREND_SAMPLE;
  const displaySample = publicationsForDisplay(sample);
  const displayPublicationCount = isTruncated
    ? data.publication_count
    : displaySample.length;
  const trend = yearHistogram(displaySample);
  const openAccessShare =
    displaySample.length > 0
      ? displaySample.filter((item) => item.is_oa).length / displaySample.length
      : null;
  const topFields = topValues(displaySample, (item) => [item.primary_field], 10);
  const displayPagination =
    !isTruncated && publications.ok
      ? {
          ...publications.value.pagination,
          total: displayPublicationCount,
          total_pages: 1,
        }
      : publications.ok
        ? publications.value.pagination
        : null;

  const breadcrumbs = (
    <nav className="text-body-sm text-muted">
      <Link href="/institutions" className="hover:text-ink hover:underline">
        Institutions
      </Link>
      <span aria-hidden> / </span>
      <span>{data.label}</span>
    </nav>
  );

  const metrics = (
    <StatTileGrid>
      <StatTile
        label="Publications"
        value={formatCompact(displayPublicationCount)}
        caption={
          isTruncated
            ? "raw accepted records with this affiliation"
            : "deduplicated records displayed for this affiliation"
        }
      />
      <StatTile
        label="Open access"
        value={
          openAccessShare === null ? "—" : formatRatioAsPercent(openAccessShare)
        }
        caption={
          isTruncated
            ? `share within the ${TREND_SAMPLE}-record sample`
            : "share of displayed institution records"
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
  );

  const overviewTab = (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <ChartPanel
        title="Publications per year"
        description={
          isTruncated
            ? `Derived from the ${TREND_SAMPLE} most recent of ${formatNumber(sampleTotal)} records — not the full history.`
            : "Derived from this institution's deduplicated publication list."
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
          <EmptyState bare title="No records with a publication year" />
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
  );

  const publicationsTab = (
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
          {displayPagination ? (
            <Pagination
              pagination={displayPagination}
              basePath={institutionHref(institutionKey)}
              searchParams={query}
            />
          ) : null}
        </div>
      )}
    </section>
  );

  const networkTab = (
    <Suspense
      fallback={<ChartSkeleton label="Loading collaboration network…" size="lg" />}
    >
      <InstitutionNetworkPanel label={data.label} />
    </Suspense>
  );

  const topicsTab =
    topFields.length > 0 ? (
      <section className="panel p-4 detail-measure">
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
                className="chip"
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
    ) : (
      <EmptyState bare title="No field assignments in the sample" />
    );

  return (
    <div className="flex flex-col gap-4">
      <PrintMeta
        title={data.label}
        snapshotDate={profile.value.meta.snapshot_date}
        extra={
          profile.value.meta.dataset_stage
            ? [`Stage: ${profile.value.meta.dataset_stage}`]
            : undefined
        }
      />
      <ProfileHeader
        title={data.label}
        subtitle={`Records span ${formatYearRange(data.year_min, data.year_max)}`}
        breadcrumbs={breadcrumbs}
        metrics={metrics}
        actions={
          <Link
            href={`/institutions/compare?institution=${encodeURIComponent(data.label)}`}
            className="interactive shrink-0 rounded-md border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:bg-wash hover:text-ink"
          >
            Compare with another →
          </Link>
        }
      />
      <ProfileTabs
        tabs={[
          { id: "overview", content: overviewTab },
          { id: "publications", content: publicationsTab },
          { id: "network", content: networkTab },
          { id: "topics", content: topicsTab, hidden: topFields.length === 0 },
        ]}
      />
      <SnapshotNote
        snapshotDate={profile.value.meta.snapshot_date}
        datasetStage={profile.value.meta.dataset_stage}
      />
    </div>
  );
}
