import Link from "next/link";

import { AnalyticsFilters, toFilterChoices, withoutQueryKey } from "@/components/analytics/AnalyticsFilters";
import { PageIntro } from "@/components/layout/PageIntro";
import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { ChartPanel, DownloadLink, MachineLegend } from "@/components/ui/ChartPanel";
import { DataTable } from "@/components/ui/DataTable";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import {
  analyticsExportUrl,
  getDatasetMeta,
  getDataQuality,
  getAnalyticsFields,
  getLimitations,
} from "@/services/api";
import { formatSnapshotDate } from "@/components/ui/Provenance";
import { PrintMeta } from "@/components/ui/PrintMeta";
import { CAPTION } from "@/services/copy";
import { extractFilters, type SearchParams } from "@/services/filters";
import { formatNumber, formatPercent } from "@/services/format";

export const metadata = {
  title: "Data quality",
  description:
    "Known limitations, missingness, and cross-source conflicts in the consolidated Sri Lankan research dataset — read before citing any figure from this platform.",
};

/** Human wording for the limitation codes returned by `/limitations`. */
const LIMITATION_TEXT: Record<string, string> = {
  observed_records_not_national_totals:
    "Every count on this platform describes records observed in the consolidated dataset. They are not official national totals, and coverage varies by source and year.",
  doi_poor_local_repositories:
    "Local and institutional repository records frequently lack DOIs, which makes them hard to deduplicate against global indexes. Some records may therefore be counted twice.",
  source_specific_missingness:
    "Different sources populate different fields. Abstracts, funding and affiliation data are far more complete for OpenAlex and Crossref records than for repository harvests.",
  cross_source_conflicts:
    "Where sources disagree on reference counts, the platform surfaces the disagreement rather than silently choosing a winner. Records with conflicts carry a flag.",
  snapshot_counts_can_lag:
    "Some source-provided counts are point-in-time values from the last data load. They can lag live values at upstream indexes.",
  author_disambiguation_limited:
    "Researcher profiles are grouped by normalised author name unless an ORCID is available. Common names may merge distinct people; name variants may split one person.",
};

const DISCLOSURE_TEXT: Record<string, string> = {
  source_snapshot_date: "The date of the data snapshot behind a figure.",
  dataset_stage: "Which pipeline stage the figure was computed over.",
  denominator: "What population a share or percentage is calculated against.",
  field_missingness: "How complete the underlying field is.",
  conflict_policy: "How disagreements between sources were resolved.",
  known_exclusions: "What the dataset is known not to cover.",
};

const BEFORE_CITING = [
  "Counts describe observed records in the consolidated dataset — not official national totals.",
  "Coverage and field completeness vary by source and year; missing DOIs and affiliations are common in repository harvests.",
  "Snapshot figures can lag live upstream indexes; always note the snapshot date shown with a chart.",
  "Violet panels mark model-generated content (classifications, match scores). Neutral surfaces hold harvested bibliographic metadata.",
] as const;

export default async function DataQualityPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const [quality, limitations, meta, fields] = await Promise.all([
    getDataQuality({ ...filters, group_by: "source_dataset" }),
    getLimitations(),
    getDatasetMeta(),
    getAnalyticsFields({ ...withoutQueryKey(filters, "field"), limit: 100 }),
  ]);

  const groups = quality.ok ? (quality.value.data.groups ?? {}) : {};
  const groupRows = Object.entries(groups)
    .map(([source, counts]) => ({ source, ...counts }))
    .sort((a, b) => b.record_count - a.record_count);

  const snapshotLabel = quality.ok
    ? formatSnapshotDate(quality.value.meta.snapshot_date)
    : null;

  return (
    <div className="flex flex-col gap-5">
      <PrintMeta
        title="Data quality"
        snapshotDate={quality.ok ? quality.value.meta.snapshot_date : null}
        searchParams={params}
      />
      <PageIntro
        title="Confidence starts with context."
        description="Understand source coverage, metadata completeness, and the limitations behind every AI research insight."
      />

      <section
        className="panel detail-measure border-warning/30 bg-wash p-4"
        aria-labelledby="before-citing-heading"
      >
        <h2
          id="before-citing-heading"
          className="font-display text-h3 text-ink"
        >
          Read this before citing
        </h2>
        <ol className="mt-3 flex list-decimal flex-col gap-2 pl-5 text-body-sm text-ink-secondary">
          {BEFORE_CITING.map((line) => (
            <li key={line} className="pl-1">
              {line}
            </li>
          ))}
        </ol>
        <MachineLegend className="mt-4 border-t border-rule pt-3" />
      </section>

      <AnalyticsFilters
        params={params}
        basePath="/data-quality"
        fields={toFilterChoices(fields.ok ? fields.value.data : [])}
      />
      {meta.ok ? (
        <StatTileGrid>
          <StatTile
            label="Collection records"
            value={formatNumber(meta.value.data.publication_count ?? null)}
            caption={CAPTION.recordsInCollection}
          />
          <StatTile
            label="Collection year coverage"
            value={
              meta.value.data.min_publication_year &&
              meta.value.data.max_publication_year
                ? `${meta.value.data.min_publication_year}–${meta.value.data.max_publication_year}`
                : "—"
            }
            caption="earliest to latest publication year"
          />
          <StatTile
            label="Dataset stage"
            value={meta.value.data.dataset_stage}
            caption="pipeline stage these figures come from"
          />
          <StatTile
            label="API version"
            value={meta.value.data.api_version}
            caption="read-only public contract"
          />
        </StatTileGrid>
      ) : null}

      <section className="panel p-4" aria-labelledby="cite-figure-heading">
        <h2 id="cite-figure-heading" className="font-display text-h3 text-ink">
          How to cite a figure
        </h2>
        <ol className="mt-3 flex list-decimal flex-col gap-2 pl-5 text-body-sm text-ink-secondary">
          <li>
            Name the chart or KPI and the filters in force (years, field,
            institution, and so on).
          </li>
          <li>
            State the snapshot date
            {snapshotLabel ? ` (currently ${snapshotLabel})` : ""} and dataset
            stage
            {meta.ok ? ` (${meta.value.data.dataset_stage})` : ""}.
          </li>
          <li>
            Give the denominator in plain language — usually “of selected AI
            publications” or “of the accepted AI collection”.
          </li>
          <li>
            Point readers to this page for known limitations and required
            disclosures.
          </li>
        </ol>
      </section>

      <section>
        <SectionHeading
          title="Known limitations"
          description="Published by the API at /limitations, so this list stays in step with the pipeline."
        />
        {!limitations.ok ? (
          <ApiErrorPanel error={limitations.error} what="the limitations list" />
        ) : (
          <details className="panel group p-0">
            <summary className="cursor-pointer list-none px-4 py-3 text-body-sm font-medium text-ink marker:content-none [&::-webkit-details-marker]:hidden">
              <span className="flex items-center justify-between gap-3">
                <span>
                  Full limitations ({limitations.value.data.limitations.length})
                </span>
                <span className="text-muted group-open:hidden" aria-hidden>
                  Show ↓
                </span>
                <span className="hidden text-muted group-open:inline" aria-hidden>
                  Hide ↑
                </span>
              </span>
            </summary>
            <ul className="flex flex-col gap-2 border-t border-rule px-4 py-3">
              {limitations.value.data.limitations.map((code) => (
                <li key={code} className="rounded-md border border-rule bg-surface p-3">
                  <h3 className="flex items-center gap-2 text-body-sm font-medium text-ink">
                    <span aria-hidden className="text-warning">
                      ▲
                    </span>
                    {code.replace(/_/g, " ")}
                  </h3>
                  <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
                    {LIMITATION_TEXT[code] ??
                      "See the metadata quality documentation for details."}
                  </p>
                </li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {quality.ok ? (
        <section className="flex flex-col gap-4">
          <SectionHeading
            title="Field completeness"
            description="Missingness across the whole dataset."
            action={
              <DownloadLink href={analyticsExportUrl("data-quality", filters)} />
            }
          />
          <StatTileGrid>
            <StatTile
              label="Records assessed"
              value={formatNumber(quality.value.data.record_count)}
              caption="denominator for the shares below"
            />
            <StatTile
              label="Missing DOI"
              value={formatPercent(quality.value.data.missing_doi_percentage)}
              caption="cannot be linked or deduplicated reliably"
            />
            <StatTile
              label="Missing abstract"
              value={formatPercent(quality.value.data.missing_abstract_percentage)}
              caption="limits text search and topic assignment"
            />
            <StatTile
              label="Missing affiliation"
              value={formatPercent(
                quality.value.data.missing_institutions_percentage,
              )}
              caption="absent from institution views"
            />
          </StatTileGrid>

          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <section className="panel p-4">
              <SectionHeading
                title="Cross-source conflicts"
                description="Records where OpenAlex and Crossref disagree."
              />
              <DataTable
                columns={[
                  { key: "kind", header: "Conflict", render: (row) => row.kind },
                  {
                    key: "count",
                    header: "Records",
                    numeric: true,
                    render: (row) => formatNumber(row.count),
                  },
                ]}
                rows={[
                  {
                    kind: "Reference counts disagree",
                    count: quality.value.data.reference_divergence_count,
                  },
                ]}
                rowKey={(row) => row.kind}
              />
              <p className="mt-3 text-body-sm text-muted">
                Conflicting records are shown with a flag on the publication page
                rather than being silently resolved to one source.
              </p>
            </section>

            {groupRows.length > 0 ? (
              <ChartPanel
                title="Records by source"
                description="Record counts contributed by each source dataset."
                table={
                  <details className="mt-3 border-t border-rule pt-3">
                    <summary className="cursor-pointer text-body-sm text-ink-secondary hover:text-ink">
                      View completeness by source
                    </summary>
                    <div className="mt-2">
                      <DataTable
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
                          {
                            key: "doi",
                            header: "Missing DOI",
                            numeric: true,
                            render: (row) => formatNumber(row.missing_doi_count),
                          },
                          {
                            key: "abstract",
                            header: "Missing abstract",
                            numeric: true,
                            render: (row) =>
                              formatNumber(row.missing_abstract_count),
                          },
                        ]}
                        rows={groupRows}
                        rowKey={(row) => row.source}
                      />
                    </div>
                  </details>
                }
              >
                <RankingBarChart
                  entries={groupRows.map((row) => ({
                    label: row.source,
                    value: row.record_count,
                  }))}
                  valueLabel="Records"
                  ariaLabel="Bar chart of record counts by source dataset"
                />
              </ChartPanel>
            ) : null}
          </div>
        </section>
      ) : (
        <ApiErrorPanel error={quality.error} what="data quality metrics" />
      )}

      {limitations.ok ? (
        <section className="panel p-4">
          <SectionHeading
            title="Required disclosures"
            description="What any chart or table derived from this dataset should state alongside its numbers."
          />
          <dl className="flex flex-col gap-2">
            {limitations.value.data.required_disclosures.map((code) => (
              <div key={code} className="border-b border-rule pb-2 last:border-0">
                <dt className="text-body-sm font-medium text-ink">
                  {code.replace(/_/g, " ")}
                </dt>
                <dd className="text-body-sm text-ink-secondary">
                  {DISCLOSURE_TEXT[code] ??
                    "See the metadata quality documentation."}
                </dd>
              </div>
            ))}
          </dl>
          <p className="mt-3 text-body-sm text-muted">
            Full documentation:{" "}
            <code className="rounded bg-wash px-1 py-0.5">
              {limitations.value.data.document}
            </code>
          </p>
        </section>
      ) : null}

      <p className="text-body-sm text-ink-secondary">
        Back to the{" "}
        <Link href="/" className="text-primary hover:underline">
          national dashboard
        </Link>
        .
      </p>
    </div>
  );
}
