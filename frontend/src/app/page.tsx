import Link from "next/link";
import { Suspense } from "react";
import { AnalyticsFilters } from "@/components/analytics/AnalyticsFilters";
import { ActivityPanel, FieldDistributionPanel, NetworkPanel, TrendPanel } from "@/components/analytics/ResearchPanels";
import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { PageIntro, ResearchHero } from "@/components/layout/PageIntro";
import { DataQualityIcon, InstitutionsIcon, OpenAccessIcon, PublicationsIcon } from "@/components/layout/NavIcons";
import { ActiveFilters } from "@/components/publications/FilterControls";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, Skeleton } from "@/components/ui/Feedback";
import { SnapshotNote } from "@/components/ui/Provenance";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { analyticsExportUrl, buildQuery, getAnalyticsFields, getAnalyticsInstitutions, getAnalyticsOverview, listPublications, type QueryParams } from "@/services/api";
import { extractFilters, type SearchParams } from "@/services/filters";
import { formatCompact, formatNumber, formatRatioAsPercent } from "@/services/format";
import { institutionHref, publicationHref } from "@/services/links";

export const metadata = { title: "AI research overview", description: "Publication trends, institutions, fields, and collaborations within Sri Lanka’s accepted AI research collection." };

export default async function DashboardPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const filters = { year_min: 2016, year_max: new Date().getFullYear(), ...extractFilters(params) };
  const [overview, fields, institutions, filterFields] = await Promise.all([getAnalyticsOverview(filters), getAnalyticsFields({ ...filters, limit: 100 }), getAnalyticsInstitutions({ ...filters, limit: 12 }), getAnalyticsFields({ ...filters, field: undefined, limit: 100 })]);
  const entries = fields.ok ? fields.value.data : [];
  return <div className="flex flex-col gap-6">
    <PageIntro title="Sri Lanka’s AI research, in focus." description="Explore the people, ideas, and connections shaping artificial intelligence research." action={<DownloadLink href={analyticsExportUrl("overview", filters)}>Export overview</DownloadLink>} />
    <ResearchHero />
    <AnalyticsFilters params={params} fields={filterFields.ok ? filterFields.value.data.map(e => e.label) : entries.map(e => e.label)} defaultFrom={2016} defaultTo={new Date().getFullYear()} />
    <ActiveFilters searchParams={params} basePath="/" />
    {!overview.ok ? <ApiErrorPanel error={overview.error} what="AI research metrics" /> : <section aria-label="AI collection metrics"><StatTileGrid>
      <StatTile label="AI publications" icon={<PublicationsIcon />} value={formatCompact(overview.value.data.publication_count)} caption="accepted AI records in this selection" />
      <StatTile label="Institutions" icon={<InstitutionsIcon />} value={institutions.ok ? formatNumber(institutions.value.pagination.total) : "—"} caption="with AI publications in this selection" />
      <StatTile label="Open access" icon={<OpenAccessIcon />} value={formatRatioAsPercent(overview.value.data.open_access_share)} caption="share of selected AI publications" />
      <StatTile label="DOI coverage" icon={<DataQualityIcon />} value={formatRatioAsPercent(overview.value.data.doi_coverage)} caption={`Abstract coverage ${formatRatioAsPercent(overview.value.data.abstract_coverage)}`} hint={`From ${overview.value.data.source_count} source datasets`} />
    </StatTileGrid><SnapshotNote snapshotDate={overview.value.meta.snapshot_date} datasetStage={overview.value.meta.dataset_stage} className="mt-3" /></section>}
    <div className="analytics-grid"><Suspense fallback={<Skeleton className="h-96" />}><TrendPanel filters={filters} /></Suspense>{fields.ok ? <FieldDistributionPanel entries={entries} filters={filters} total={overview.ok ? overview.value.data.publication_count : undefined} /> : <ApiErrorPanel error={fields.error} what="research fields" />}</div>
    <div className="grid min-w-0 grid-cols-1 gap-5 xl:grid-cols-2">
      <ChartPanel title="Institutions advancing AI research" description="Leading institutions by AI publication count." action={<DownloadLink href={analyticsExportUrl("institutions", filters)} />} table={institutions.ok ? <TableDisclosure><DataTable rows={institutions.value.data} rowKey={r => r.key} columns={[{ key: "name", header: "Institution", render: r => <Link href={institutionHref(r.label)} className="hover:underline">{r.label}</Link> }, { key: "count", header: "AI publications", numeric: true, render: r => formatNumber(r.publication_count) }]} /></TableDisclosure> : null}>
        {institutions.ok ? <RankingBarChart entries={institutions.value.data.map(r => ({ label: r.label, value: r.publication_count }))} valueLabel="AI publications" ariaLabel="Leading institutions by AI publication count" /> : <ApiErrorPanel error={institutions.error} what="institution rankings" />}
        <Link href={`/institutions${buildQuery(filters)}`} className="mt-4 inline-block text-xs text-primary hover:underline">Browse institutions →</Link>
      </ChartPanel>
      <Suspense fallback={<Skeleton className="h-96" />}><ActivityPanel filters={filters} fields={entries.map(e => e.label)} /></Suspense>
    </div>
    <Suspense fallback={<Skeleton className="h-[30rem]" />}><NetworkPanel filters={filters} /></Suspense>
    <Suspense fallback={<Skeleton className="h-60" />}><RecentPublications filters={filters} /></Suspense>
  </div>;
}

async function RecentPublications({ filters }: { filters: QueryParams }) {
  const result = await listPublications({ ...filters, sort: "year_desc", page_size: 5 });
  if (!result.ok) return <ApiErrorPanel error={result.error} what="recent publications" />;
  return <ChartPanel title="A closer look at AI research" description="Recent publications in the current selection." action={<Link href={`/publications${buildQuery(filters)}`} className="text-xs text-primary hover:underline">Browse AI publications →</Link>}><DataTable rows={result.value.data} rowKey={r => r.publication_key} columns={[
    { key: "title", header: "Publication", render: r => <div><Link href={publicationHref(r.publication_key)} className="font-medium text-ink hover:text-primary">{r.title ?? "Untitled record"}</Link><p className="mt-1 text-xs text-muted">{r.authors.slice(0, 3).join(", ")}</p></div> },
    { key: "field", header: "Field", render: r => r.primary_field ?? "Unclassified" },
    { key: "year", header: "Year", numeric: true, render: r => r.publication_year ?? "—" },
    { key: "access", header: "Access", render: r => r.is_oa ? <span className="rounded bg-primary-muted px-2 py-1 text-xs text-primary">Open access</span> : "Not marked open" },
  ]} /></ChartPanel>;
}
