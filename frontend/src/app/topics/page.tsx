import { CsvDownload } from "@/components/ui/CsvDownload";
import { Suspense } from "react";
import { AnalyticsFilters, toFilterChoices, withoutQueryKey } from "@/components/analytics/AnalyticsFilters";
import { ActivityPanel } from "@/components/analytics/ResearchPanels";
import { DistributionChart, type MosaicEntry } from "@/components/charts/DistributionChart";
import { PageIntro } from "@/components/layout/PageIntro";
import Link from "next/link";

import { ChartPanel, ChartSkeleton, DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState, SectionHeading, emptyListState } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { PrintMeta } from "@/components/ui/PrintMeta";
import { analyticsExportUrl, buildQuery, listFields, listTopics, getAnalyticsFields, type QueryParams } from "@/services/api";
import { extractFilters, extractMinCount, extractPage, type SearchParams } from "@/services/filters";
import { publicationSearchHref, topicHref } from "@/services/links";

async function subfieldBranches(
  filters: QueryParams,
  labels: string[],
): Promise<Record<string, MosaicEntry[]>> {
  const results = await Promise.all(
    labels.map(async (label) => {
      const result = await listFields({
        ...filters,
        field: [label],
        level: "subfield",
        page: 1,
        page_size: 12,
      });
      const children = result.ok
        ? result.value.data
            .filter((row) => row.publication_count > 0)
            .map((row) => ({ label: row.label, value: row.publication_count }))
        : [];
      return [label, children] as const;
    }),
  );
  return Object.fromEntries(results);
}

export const metadata = {
  title: "Topics and fields",
  description:
    "Research topics and fields across the Sri Lankan corpus, showing where output concentrates and which areas are under-represented.",
};

const LEVELS = [
  { value: "domain", label: "Domain" },
  { value: "field", label: "Field" },
  { value: "subfield", label: "Subfield" },
] as const;

type Level = (typeof LEVELS)[number]["value"];

export default async function TopicsPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const minCount = extractMinCount(params);
  const rawLevel = typeof params.level === "string" ? params.level : "field";
  const level: Level = LEVELS.some((option) => option.value === rawLevel)
    ? (rawLevel as Level)
    : "field";
  const fieldsPage = extractPage(params, "fields_page");
  const topicsPage = extractPage(params, "topics_page");

  const [fields, topics, filterFields] = await Promise.all([
    listFields({
      ...filters,
      ...(minCount ? { min_count: minCount } : {}),
      level,
      page: fieldsPage,
      page_size: 25,
    }),
    listTopics({ ...filters, source: "openalex", page: topicsPage, page_size: 25 }),
    getAnalyticsFields({ ...withoutQueryKey(filters, "field"), limit: 100 }),
  ]);
  const fieldBranches =
    level === "field" && fields.ok
      ? await subfieldBranches(
          filters,
          fields.value.data.map((entry) => entry.label),
        )
      : {};

  return (
    <div className="flex flex-col gap-3">
      <PrintMeta
        title="Topics and fields"
        snapshotDate={topics.ok ? topics.value.meta.snapshot_date : null}
        searchParams={params}
      />
      <PageIntro
        title="Topics and fields"
        description="OpenAlex fields and topics in the Sri Lankan AI corpus, ranked by publication count."
      />

      <AnalyticsFilters
        params={params}
        basePath="/topics"
        fields={toFilterChoices(filterFields.ok ? filterFields.value.data : [])}
        showMinCount
      />

      <section>
        <SectionHeading
          title="Classification breakdown"
          description="Drill Domain → Field → Subfield. Counts are assignment tallies, not exclusive shares."
          action={
            <nav aria-label="Classification level">
              <ol className="flex flex-wrap items-center gap-1">
                {LEVELS.map((option, index) => (
                  <li key={option.value} className="flex items-center gap-1">
                    {index > 0 ? (
                      <span aria-hidden className="text-muted">
                        →
                      </span>
                    ) : null}
                    <Link
                      href={`/topics${buildQuery({ ...filters, level: option.value })}`}
                      aria-current={option.value === level ? "true" : undefined}
                      className={`interactive inline-block rounded-md border px-2.5 py-1 text-body-sm ${
                        option.value === level
                          ? "border-primary font-medium text-primary"
                          : "border-rule text-ink-secondary hover:bg-wash"
                      }`}
                    >
                      {option.label}
                    </Link>
                  </li>
                ))}
              </ol>
            </nav>
          }
        />

        {!fields.ok ? (
          <ApiErrorPanel error={fields.error} what="the field breakdown" />
        ) : fields.value.data.length === 0 ? (
          <EmptyState {...emptyListState("classification results", "/topics", filters)} />
        ) : (
          <ChartPanel
            title={`Publications by ${level}`}
            action={<div className="flex flex-wrap gap-2"><CsvDownload filename={`ai-${level}-page-${fieldsPage}.csv`} headers={[level, "AI publications"]} rows={fields.value.data.map(e => [e.label, e.publication_count])} />{level === "field" ? <DownloadLink href={analyticsExportUrl("fields", filters)}>All fields CSV</DownloadLink> : null}</div>}
            table={
              <details className="mt-3 border-t border-rule pt-3">
                <summary className="cursor-pointer text-body-sm text-ink-secondary hover:text-ink">
                  View as table
                </summary>
                <div className="mt-2">
                  <RankingTable
                    entries={fields.value.data}
                    labelHeader={level}
                    rankOffset={
                      (fields.value.pagination.page - 1) *
                      fields.value.pagination.page_size
                    }
                    href={(label) =>
                      publicationSearchHref(
                        level === "subfield"
                          ? { subfield: label }
                          : level === "domain"
                            ? { domain: label }
                          : { field: label },
                      )
                    }
                  />
                  <div className="mt-3">
                    <Pagination
                      pagination={fields.value.pagination}
                      basePath="/topics"
                      searchParams={params}
                      pageParam="fields_page"
                    />
                  </div>
                </div>
              </details>
            }
          >
            <DistributionChart
              entries={fields.value.data.map((entry) => ({
                label: entry.label,
                value: entry.publication_count,
              }))}
              branches={fieldBranches}
              initialView="mosaic"
              ariaLabel={
                level === "field"
                  ? "AI publications by field. Select a field to open its subfields."
                  : `AI publication distribution by ${level}`
              }
            />
            <p className="mt-3 text-body-sm text-muted">
              Counts on this page.
              {level === "field" ? " Select a field to open its subfields." : ""}
            </p>
          </ChartPanel>
        )}
      </section>

      {level === "field" && fields.ok ? <Suspense fallback={<ChartSkeleton label="Loading field activity…" size="lg" />}><ActivityPanel filters={filters} fields={fields.value.data.map(f => f.label)} /></Suspense> : null}

      <section>
        <SectionHeading
          title="Topics"
          description="Fine-grained OpenAlex topic assignments, ranked by publication count."
        />
        {!topics.ok ? (
          <details className="panel p-4" open>
            <summary className="cursor-pointer font-medium text-ink">
              Topic directory unavailable
            </summary>
            <div className="mt-3">
              <ApiErrorPanel error={topics.error} what="the topic directory" />
              <p className="mt-3 text-body-sm text-ink-secondary">
                Classification fields above may still load. Try Domain / Field /
                Subfield, or clear filters.
              </p>
            </div>
          </details>
        ) : topics.value.data.length === 0 ? (
          <EmptyState {...emptyListState("topics", "/topics", filters)} />
        ) : (
          <>
            <div className="panel p-1">
              <RankingTable
                fitWidth
                entries={topics.value.data}
                labelHeader="Topic"
                href={topicHref}
                rankOffset={
                  (topics.value.pagination.page - 1) *
                  topics.value.pagination.page_size
                }
              />
            </div>
            <div className="mt-3">
              <Pagination
                pagination={topics.value.pagination}
                basePath="/topics"
                searchParams={params}
                pageParam="topics_page"
              />
            </div>
          </>
        )}
      </section>

      {topics.ok ? (
        <SnapshotNote
          snapshotDate={topics.value.meta.snapshot_date}
          datasetStage={topics.value.meta.dataset_stage}
        />
      ) : null}
    </div>
  );
}
