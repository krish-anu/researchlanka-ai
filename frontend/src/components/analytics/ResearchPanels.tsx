import { CsvDownload } from "@/components/ui/CsvDownload";
import Link from "next/link";
import { ActivityHeatmap } from "@/components/charts/ActivityHeatmap";
import { DistributionChart } from "@/components/charts/DistributionChart";
import { InstitutionScatterChart } from "@/components/charts/InstitutionScatterChart";
import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { CollaborationNetwork } from "@/components/network/CollaborationNetwork";
import { NetworkBrokersTable, NetworkSummaryPanel } from "@/components/network/NetworkMetrics";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import { ApiErrorPanel, EmptyState } from "@/components/ui/Feedback";
import { getAnalyticsTrends, getCollaborationNetwork, analyticsExportUrl, buildQuery, type QueryParams } from "@/services/api";
import { formatNumber, formatRatioAsPercent } from "@/services/format";
import { institutionHref } from "@/services/links";
import type { RankingEntry, TrendPoint } from "@/types/api";

/** An open-access subset of an explicitly non-open selection is empty. */
function openAccessTrends(filters: QueryParams & { group_by?: "year" | "institution" }) {
  if (filters.is_oa === false || filters.is_oa === "false") {
    return Promise.resolve({ ok: true as const, value: { data: [] as TrendPoint[] } });
  }
  return getAnalyticsTrends({ ...filters, is_oa: true });
}

export async function TrendPanel({ filters }: { filters: QueryParams }) {
  const params = { ...filters, group_by: "year" as const };
  const [result, openAccess] = await Promise.all([getAnalyticsTrends(params), openAccessTrends(params)]);
  if (!result.ok) return <ApiErrorPanel error={result.error} what="AI publication trends" />;
  const points = [...result.value.data].sort((a, b) => Number(a.key) - Number(b.key));
  const oa = new Map(openAccess.ok ? openAccess.value.data.map(p => [String(p.key), p.publication_count]) : []);
  return <ChartPanel title="AI research output over time" description="Annual AI publications and their open access subset." action={<DownloadLink href={analyticsExportUrl("trends", params)} />} table={<TableDisclosure><DataTable rows={points} rowKey={p => String(p.key)} columns={[
    { key: "year", header: "Year", render: p => String(p.key) },
    { key: "count", header: "AI publications", numeric: true, render: p => formatNumber(p.publication_count) },
    { key: "oa", header: "Open access", numeric: true, render: p => openAccess.ok ? formatNumber(oa.get(String(p.key)) ?? 0) : "Unavailable" },
  ]} /></TableDisclosure>}>
    {points.length ? <TrendLineChart points={points.map(p => ({ key: p.key, value: p.publication_count }))} valueLabel="AI publications" ariaLabel="AI publication output by year" secondary={openAccess.ok ? { label: "Open access", points: points.map(p => ({ key: p.key, value: oa.get(String(p.key)) ?? 0 })) } : undefined} /> : <EmptyState title="No annual data in this selection" />}
    {!openAccess.ok ? <p className="mt-2 text-xs text-muted">Open access comparison could not be loaded. Total publication counts are shown.</p> : null}
  </ChartPanel>;
}

export function FieldDistributionPanel({ entries, filters, total }: { entries: RankingEntry[]; filters: QueryParams; total?: number }) {
  const leading = entries.slice(0, 5).map(e => ({ label: e.label, value: e.publication_count }));
  const represented = entries.reduce((sum, e) => sum + e.publication_count, 0);
  const remaining = Math.max(0, (total ?? represented) - leading.reduce((sum, e) => sum + e.value, 0));
  const tableRows = [...entries.map(e => ({ label: e.label, value: e.publication_count })), ...(total !== undefined && total > represented ? [{ label: "Other / unclassified", value: total - represented }] : [])];
  const slices = [...leading, ...(remaining ? [{ label: total === undefined ? "Other displayed fields" : "Other / unclassified", value: remaining }] : [])];
  return <ChartPanel title="The AI research landscape" description="Primary research fields within the AI publication collection." action={<DownloadLink href={analyticsExportUrl("fields", filters)} />} table={<TableDisclosure><DataTable rows={tableRows} rowKey={e => e.label} columns={[{ key: "field", header: "Field", render: e => e.label === "Other / unclassified" ? e.label : <Link href={`/publications${buildQuery({ ...filters, field: [e.label] })}`} className="hover:underline">{e.label}</Link> }, { key: "count", header: "AI publications", numeric: true, render: e => formatNumber(e.value) }]} /></TableDisclosure>}>
    {slices.length ? <DistributionChart entries={slices} ariaLabel="Share of AI publications by primary research field" /> : <EmptyState title="No field data in this selection" />}
    <p className="mt-4 text-xs text-muted">{total === undefined ? "Shares describe the displayed field counts." : "Other / unclassified includes fields outside the top five and records without a primary field."}</p>
  </ChartPanel>;
}

export async function ActivityPanel({ filters, fields }: { filters: QueryParams; fields: string[] }) {
  const lastYear = Number(filters.year_max) || new Date().getFullYear();
  const firstYear = Math.max(Number(filters.year_min) || lastYear - 4, lastYear - 4);
  const years = Array.from({ length: Math.max(0, Math.min(5, lastYear - firstYear + 1)) }, (_, i) => firstYear + i);
  const selected = fields.slice(0, 5);
  if (!selected.length || !years.length) return <EmptyState title="No field activity in this selection" />;
  const results = await Promise.all(selected.map(field => getAnalyticsTrends({ ...filters, field: [field], year_min: firstYear, year_max: lastYear, group_by: "year" })));
  const failure = results.find(result => !result.ok);
  if (failure && !failure.ok) return <ApiErrorPanel error={failure.error} what="field activity" />;
  const rows = results.map((result, i) => ({ label: selected[i], values: years.map(year => result.ok ? result.value.data.find(p => Number(p.key) === year)?.publication_count ?? 0 : 0) }));
  return <ChartPanel title="Where AI research is growing" description={`Annual activity in the leading fields · ${firstYear}–${lastYear}`} action={<CsvDownload filename="ai-field-activity.csv" headers={["Field", ...years.map(String)]} rows={rows.map(r => [r.label, ...r.values])} />} table={<TableDisclosure><DataTable rows={rows} rowKey={r => r.label} columns={[{ key: "field", header: "Field", render: r => r.label }, ...years.map((year, i) => ({ key: String(year), header: String(year), numeric: true, render: (r: typeof rows[number]) => formatNumber(r.values[i]) }))]} /></TableDisclosure>}><ActivityHeatmap years={years} rows={rows} /><p className="mt-3 text-xs text-muted">Darker cells indicate more publications. Counts are printed in each cell; use the table for exact values.</p></ChartPanel>;
}

export async function InstitutionAccessibilityPanel({ filters, entries }: { filters: QueryParams; entries: RankingEntry[] }) {
  const openAccess = await openAccessTrends({ ...filters, group_by: "institution" });
  if (!openAccess.ok) return <ApiErrorPanel error={openAccess.error} what="institution open access data" />;
  const counts = new Map(openAccess.value.data.map(row => [String(row.key), row.publication_count]));
  const points = entries.slice(0, 15).filter(e => e.publication_count > 0).map(e => ({ label: e.label, publications: e.publication_count, openAccessShare: (counts.get(e.label) ?? 0) / e.publication_count }));
  return <ChartPanel title="Output & accessibility" description="Publication volume and open access share for the displayed institutions." action={<CsvDownload filename="ai-institution-accessibility.csv" headers={["Institution", "AI publications", "Open access share"]} rows={points.map(p => [p.label, p.publications, p.openAccessShare])} />} table={<TableDisclosure><DataTable rows={points} rowKey={p => p.label} columns={[{ key: "name", header: "Institution", render: p => <Link href={institutionHref(p.label)} className="hover:underline">{p.label}</Link> }, { key: "count", header: "AI publications", numeric: true, render: p => formatNumber(p.publications) }, { key: "oa", header: "Open access", numeric: true, render: p => formatRatioAsPercent(p.openAccessShare) }]} /></TableDisclosure>}><InstitutionScatterChart points={points} /><p className="mt-3 text-xs text-muted">Hover over an institution for its exact values. Each share uses that institution’s selected AI publications.</p></ChartPanel>;
}

export async function NetworkPanel({ filters, scope = "institution", limit = 120, minWeight = 1 }: { filters: QueryParams; scope?: "institution" | "country" | "researcher"; limit?: number; minWeight?: number }) {
  const network = await getCollaborationNetwork({ ...filters, scope, limit, min_weight: minWeight });
  if (!network.ok) return <ApiErrorPanel error={network.error} what="the collaboration network" />;
  return <ChartPanel title="AI research is a shared endeavour" description="Connections formed by shared AI publications." action={<div className="flex flex-wrap items-center gap-3"><Link href="/collaboration" className="text-xs text-primary hover:underline">Explore collaborations →</Link><CsvDownload filename="ai-collaboration-pairs.csv" headers={["Entity", "Collaborator", "Shared AI publications"]} rows={network.value.data.edges.map(e => [e.source_label ?? e.source, e.target_label ?? e.target, e.weight])} /></div>} table={<TableDisclosure label="View collaboration pairs as table"><DataTable rows={network.value.data.edges} rowKey={(r, i) => `${r.source}-${r.target}-${i}`} columns={[{ key: "source", header: "Entity", render: r => r.source_label ?? r.source }, { key: "target", header: "Collaborator", render: r => r.target_label ?? r.target }, { key: "weight", header: "Shared AI publications", numeric: true, render: r => formatNumber(r.weight) }]} /></TableDisclosure>}>
    <div className="flex flex-col gap-5"><CollaborationNetwork network={network.value.data} scope={scope} /><NetworkSummaryPanel summary={network.value.data.summary} /><div><h3 className="mb-2 text-h3">Bridging {scope === "institution" ? "institutions" : scope === "researcher" ? "researchers" : "countries"}</h3><p className="mb-3 text-xs text-muted">Ranked by their role connecting otherwise separate groups, rather than publication volume.</p><NetworkBrokersTable nodes={network.value.data.nodes} /></div></div>
  </ChartPanel>;
}
