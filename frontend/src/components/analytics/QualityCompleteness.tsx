import { ChartPanel } from "@/components/ui/ChartPanel";
import { DataTable, TableDisclosure } from "@/components/ui/DataTable";
import type { DataQualitySummary } from "@/types/api";

export function QualityCompleteness({ groups }: { groups: NonNullable<DataQualitySummary["groups"]> }) {
  const rows = Object.entries(groups).map(([label, group]) => ({ label, count: group.record_count, doi: group.record_count ? 100 * (group.record_count - group.missing_doi_count) / group.record_count : null, abstract: group.record_count ? 100 * (group.record_count - group.missing_abstract_count) / group.record_count : null }));
  const percent = (value: number | null) => value === null ? "—" : `${value.toFixed(1)}%`;
  return <ChartPanel title="Metadata completeness by source" description="Share of AI-related source records with each metadata field." table={<TableDisclosure><DataTable rows={rows} rowKey={r => r.label} columns={[{ key: "source", header: "Source", render: r => r.label }, { key: "count", header: "Records", numeric: true, render: r => r.count.toLocaleString() }, { key: "doi", header: "DOI present", numeric: true, render: r => percent(r.doi) }, { key: "abstract", header: "Abstract present", numeric: true, render: r => percent(r.abstract) }]} /></TableDisclosure>}>
    <div className="space-y-6">{rows.map(row => <div key={row.label}><h3 className="mb-3 text-sm font-medium">{row.label}</h3>{([['doi', 'DOI'], ['abstract', 'Abstract']] as const).map(([key, label], i) => <div key={key} className="my-2 grid grid-cols-[60px_1fr_50px] items-center gap-3 text-xs"><span className="text-muted">{label}</span><div className="h-2.5 overflow-hidden rounded-full bg-wash" role="img" aria-label={`${row.label}: ${percent(row[key])} have ${label}`}><div style={{ width: `${row[key] ?? 0}%`, background: i === 0 ? "var(--seq-450)" : "var(--series-2)" }} className="h-full rounded-full" /></div><span className="text-right tabular">{percent(row[key])}</span></div>)}</div>)}</div>
    <p className="mt-5 text-xs text-muted">Each percentage uses that source’s AI records as its denominator. Records may appear in multiple sources.</p>
  </ChartPanel>;
}
