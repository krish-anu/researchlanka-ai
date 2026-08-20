import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { ChartPanel } from "@/components/ui/ChartPanel";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { getDatasetMeta, getHealth, getDataQuality, getLimitations } from "@/services/api";
import { formatDate, formatNumber, formatPercent } from "@/services/format";

export const metadata = { title: "Pipeline" };

interface SourceRow {
  source: string;
  record_count: number;
  missing_doi_count: number;
  missing_abstract_count: number;
}

/**
 * Data-source console.
 *
 * The Stitch screen shows per-source "last run" and "records added" columns.
 * The API exposes neither: `/meta` carries one dataset-wide `max_loaded_at`,
 * and `/analytics/data-quality?group_by=source_dataset` carries per-source
 * volumes and missingness but no run history. Rather than invent a run log,
 * this screen reports what is actually knowable per source — volume and field
 * completeness — and states the load timestamp once, for the dataset as a whole.
 */
export default async function AdminPipelinePage() {
  const [meta, health, quality, limitations] = await Promise.all([
    getDatasetMeta(),
    getHealth(),
    getDataQuality({ group_by: "source_dataset" }),
    getLimitations(),
  ]);

  const groups = quality.ok ? (quality.value.data.groups ?? {}) : {};
  const rows: SourceRow[] = Object.entries(groups)
    .map(([source, counts]) => ({ source, ...counts }))
    .sort((a, b) => b.record_count - a.record_count);

  const total = rows.reduce((sum, row) => sum + row.record_count, 0);

  return (
    <div className="flex flex-col gap-8">
      <section>
        <SectionHeading title="Service" />
        <div className="panel p-5">
          <dl className="grid gap-x-8 gap-y-3 sm:grid-cols-2">
            <Row
              label="API status"
              value={
                health.ok
                  ? health.value.data.status === "ok"
                    ? "Healthy"
                    : "Unavailable"
                  : "No response"
              }
            />
            <Row
              label="API contract"
              value={health.ok ? health.value.data.api_version : "—"}
            />
            <Row
              label="Dataset stage"
              value={meta.ok ? meta.value.data.dataset_stage : "—"}
            />
            <Row
              label="Last record loaded"
              value={formatDate(meta.ok ? meta.value.data.max_loaded_at ?? null : null)}
            />
            <Row
              label="Last record updated"
              value={formatDate(meta.ok ? meta.value.data.max_updated_at ?? null : null)}
            />
            <Row
              label="Records"
              value={formatNumber(meta.ok ? meta.value.data.publication_count ?? null : null)}
            />
          </dl>
          <p className="mt-4 border-t border-rule pt-3 text-body-sm text-muted">
            Ingestion runs on a schedule outside this application. The API does
            not publish a per-source run history, so this console reports load
            timestamps and source volumes rather than job status.
          </p>
        </div>
      </section>

      <section>
        <SectionHeading
          title="Sources"
          description="Volume and field completeness per source dataset. Missingness is what drives the deduplication and enrichment backlog."
        />
        {!quality.ok ? (
          <ApiErrorPanel error={quality.error} what="the per-source breakdown" />
        ) : (
          <>
            <div className="panel p-2">
              <DataTable<SourceRow>
                rows={rows}
                rowKey={(row) => row.source}
                emptyMessage="The API returned no per-source grouping."
                columns={sourceColumns(total)}
              />
            </div>

            <div className="mt-6">
              <ChartPanel
                title="Records by source"
                description="Share of the consolidated corpus contributed by each source dataset."
                table={
                  <DataTable<SourceRow>
                    rows={rows}
                    rowKey={(row) => row.source}
                    columns={[
                      {
                        key: "source",
                        header: "Source",
                        render: (row) => row.source,
                      },
                      {
                        key: "records",
                        header: "Records",
                        numeric: true,
                        render: (row) => formatNumber(row.record_count),
                      },
                    ]}
                  />
                }
              >
                <RankingBarChart
                  entries={rows.map((row) => ({
                    label: row.source,
                    value: row.record_count,
                  }))}
                  valueLabel="Records"
                  ariaLabel="Records contributed by each source dataset"
                />
              </ChartPanel>
            </div>
          </>
        )}
      </section>

      <section>
        <SectionHeading
          title="Declared limitations"
          description="Published by the API at /limitations. Anything listed here constrains what the console's figures can be used for."
        />
        {!limitations.ok ? (
          <ApiErrorPanel error={limitations.error} what="the limitations list" />
        ) : (
          <ul className="flex flex-col gap-2">
            {limitations.value.data.limitations.map((code) => (
              <li key={code} className="panel px-4 py-3">
                <code className="data-mono text-ink-secondary">{code}</code>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

function sourceColumns(total: number): Column<SourceRow>[] {
  return [
    {
      key: "source",
      header: "Source",
      render: (row) => (
        <span className="font-medium text-ink">{row.source}</span>
      ),
    },
    {
      key: "records",
      header: "Records",
      numeric: true,
      render: (row) => formatNumber(row.record_count),
    },
    {
      key: "share",
      header: "Share",
      numeric: true,
      render: (row) =>
        total > 0 ? formatPercent((row.record_count / total) * 100) : "—",
    },
    {
      key: "doi",
      header: "Missing DOI",
      numeric: true,
      render: (row) =>
        row.record_count > 0
          ? formatPercent((row.missing_doi_count / row.record_count) * 100)
          : "—",
    },
    {
      key: "abstract",
      header: "Missing abstract",
      numeric: true,
      render: (row) =>
        row.record_count > 0
          ? formatPercent((row.missing_abstract_count / row.record_count) * 100)
          : "—",
    },
  ];
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule pb-2">
      <dt className="label-caps text-muted">{label}</dt>
      <dd className="text-body-sm text-ink">{value}</dd>
    </div>
  );
}
