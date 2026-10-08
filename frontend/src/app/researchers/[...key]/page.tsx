import Link from "next/link";
import { notFound } from "next/navigation";
import { Suspense } from "react";

import { AnalyticsFilters, toFilterChoices } from "@/components/analytics/AnalyticsFilters";
import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { ProfileHeader, ProfileTabs } from "@/components/layout/ProfileHeader";
import { ResearcherNetworkPanel } from "@/components/network/ProfileNetworkPanels";
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
  findAuthorProfilesByName,
  getAnalyticsFields,
  getResearcher,
  getResearcherCoauthors,
  getResearcherPublications,
  isNotFound,
} from "@/services/api";
import { topValues, yearHistogram } from "@/services/derive";
import {
  extractFilters,
  extractPage,
  hasActiveFilters,
  type SearchParams,
} from "@/services/filters";
import {
  formatCompact,
  formatNumber,
  formatYearRange,
  personName,
} from "@/services/format";
import {
  authorProfileHref,
  decodeKeySegments,
  publicationSearchHref,
  researcherHref,
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
const TREND_SAMPLE = 100;

export default async function ResearcherProfilePage({
  params,
  searchParams,
}: PageProps) {
  const { key } = await params;
  const query = await searchParams;
  const researcherKey = decodeKeySegments(key);
  const page = extractPage(query);
  const extractedFilters = extractFilters(query);
  const profileFilters = {
    ...(typeof extractedFilters.year_min === "number"
      ? { year_min: extractedFilters.year_min }
      : {}),
    ...(typeof extractedFilters.year_max === "number"
      ? { year_max: extractedFilters.year_max }
      : {}),
    ...(Array.isArray(extractedFilters.field)
      ? { field: extractedFilters.field }
      : {}),
  };
  const filtersActive = hasActiveFilters(profileFilters);

  const profile = await getResearcher(researcherKey);
  if (isNotFound(profile)) notFound();
  if (!profile.ok) {
    return <ApiErrorPanel error={profile.error} what="this researcher profile" />;
  }

  const data = profile.value.data;
  const [publications, coauthors, trendSample, fields, verified] = await Promise.all([
    getResearcherPublications(researcherKey, {
      ...profileFilters,
      page,
      page_size: PAGE_SIZE,
    }),
    getResearcherCoauthors(researcherKey, { limit: 25 }),
    getResearcherPublications(researcherKey, {
      ...profileFilters,
      page: 1,
      page_size: TREND_SAMPLE,
    }),
    getAnalyticsFields({
      researcher: [researcherKey],
      ...(typeof profileFilters.year_min === "number"
        ? { year_min: profileFilters.year_min }
        : {}),
      ...(typeof profileFilters.year_max === "number"
        ? { year_max: profileFilters.year_max }
        : {}),
      limit: 100,
    }),
    findAuthorProfilesByName(data.label),
  ]);
  const verifiedProfiles = verified.ok ? verified.value.data : [];
  // "claimed": the profile holds approved claims on this exact spelling.
  const claimedBy = verifiedProfiles.filter((match) => match.match === "claimed");
  const similar = verifiedProfiles.filter((match) => match.match !== "claimed");

  const sample = trendSample.ok ? trendSample.value.data : [];
  const sampleTotal = trendSample.ok ? trendSample.value.pagination.total : 0;
  const trend = yearHistogram(sample);
  const isTruncated = sampleTotal > TREND_SAMPLE;
  const topFields = topValues(sample, (item) => [item.primary_field]);

  const breadcrumbs = (
    <nav className="text-body-sm text-muted">
      <Link href="/researchers" className="hover:text-ink hover:underline">
        Researchers
      </Link>
      <span aria-hidden> / </span>
      <span>{personName(data.label)}</span>
    </nav>
  );

  const notice = (
    <div className="flex flex-col gap-2">
      {claimedBy.length > 0 ? (
        <div className="panel border-good/40 p-3 detail-measure">
          <p className="text-body-sm text-ink-secondary">
            <span aria-hidden className="mr-2 text-success-text">
              ✓
            </span>
            {claimedBy.map((match, index) => (
              <span key={match.slug}>
                {index > 0 ? "; " : ""}
                <strong className="font-medium text-ink">{match.claimed_count}</strong> of the publications
                under this spelling belong to{" "}
                <Link href={authorProfileHref(match.slug)} className="font-medium text-primary hover:underline">
                  {match.display_name}
                </Link>
                {match.institution ? ` (${match.institution})` : ""}
              </span>
            ))}
            . Their verified profile brings together every spelling of their name.
          </p>
        </div>
      ) : null}
      {similar.length > 0 ? (
        <div className="panel p-3 detail-measure">
          <p className="text-body-sm text-ink-secondary">
            {similar.length === 1 ? "A verified author with a similar name: " : "Verified authors with similar names: "}
            {similar.map((match, index) => (
              <span key={match.slug}>
                {index > 0 ? "; " : ""}
                <Link href={authorProfileHref(match.slug)} className="font-medium text-primary hover:underline">
                  {match.display_name}
                </Link>
                {match.institution ? ` (${match.institution})` : ""}
              </span>
            ))}
            . Their profile lists only the publications they claimed and an administrator approved.
          </p>
        </div>
      ) : null}
      <div className="panel border-warning/40 p-3 detail-measure">
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
            , not a verified identifier. Records from different people sharing this
            name may be combined here.{" "}
            <Link href="/data-quality" className="text-primary hover:underline">
              Data quality
            </Link>
          </span>
        </p>
      </div>
    </div>
  );

  const metrics = (
    <StatTileGrid>
      <StatTile
        label="Publications"
        value={formatCompact(data.publication_count)}
        caption="lifetime records attributed to this name"
      />
      <StatTile
        label="Active years"
        value={formatYearRange(data.year_min, data.year_max)}
        caption="first to most recent record"
      />
      <StatTile
        label="Co-authors"
        value={coauthors.ok ? formatNumber(coauthors.value.data.length) : "—"}
        caption="distinct collaborators (top 25 shown)"
      />
    </StatTileGrid>
  );

  const overviewTab = (
    <>
      <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-2">
        <ChartPanel
          title="Publications per year"
          description={
            isTruncated
              ? `Derived from the ${TREND_SAMPLE} most recent of ${formatNumber(sampleTotal)} records — not the full history.`
              : filtersActive
                ? "Derived from publications matching the current filters."
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
            title="Co-authors"
            description="Most frequent collaborators across the full publication history."
          />
          {!coauthors.ok ? (
            <ApiErrorPanel error={coauthors.error} what="co-authors" />
          ) : coauthors.value.data.length === 0 ? (
            <EmptyState bare title="No co-authors recorded for this researcher" />
          ) : (
            <div className="max-h-80 overflow-y-auto">
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
                      {personName(row.name)}
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
            </div>
          )}
        </section>
      </div>
    </>
  );

  const publicationsTab = (
    <section>
      <SectionHeading
        title="Publications"
        description={
          filtersActive && publications.ok
            ? `${formatNumber(publications.value.pagination.total)} matching records, newest first.`
            : "Every record attributed to this name, newest first."
        }
        action={
          <DownloadLink
            href={exportUrl("publications.csv", {
              ...profileFilters,
              researcher: [data.label],
            })}
          >
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
  );

  const networkTab = (
    <Suspense
      fallback={<ChartSkeleton label="Loading collaboration network…" size="lg" />}
    >
      <ResearcherNetworkPanel label={data.label} filters={profileFilters} />
    </Suspense>
  );

  const topicsTab =
    topFields.length > 0 ? (
      <section className="panel p-4 detail-measure">
        <SectionHeading
          title="Publishes in"
          description="Fields most represented across the sampled publication list."
        />
        <ul className="flex flex-wrap gap-2">
          {topFields.map((entry) => (
            <li key={entry.label}>
              <Link
                href={publicationSearchHref({ field: entry.label })}
                className="chip"
              >
                {entry.label}
                <span className="data-mono text-muted">{entry.count}</span>
              </Link>
            </li>
          ))}
        </ul>
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
        title={personName(data.label)}
        subtitle={`Active ${formatYearRange(data.year_min, data.year_max)}`}
        breadcrumbs={breadcrumbs}
        notice={notice}
        metrics={metrics}
      />
      <AnalyticsFilters
        params={query}
        fields={toFilterChoices(fields.ok ? fields.value.data : [])}
        basePath={researcherHref(researcherKey)}
        title="Publication filters"
        summaryLabel="Showing"
        yearPhrase="Publication years"
        applyLabel="Apply filters"
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
