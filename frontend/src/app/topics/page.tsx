import { CsvDownload } from "@/components/ui/CsvDownload";
import { Suspense } from "react";
import { AnalyticsFilters } from "@/components/analytics/AnalyticsFilters";
import { ActivityPanel } from "@/components/analytics/ResearchPanels";
import { DistributionChart } from "@/components/charts/DistributionChart";
import { PageIntro } from "@/components/layout/PageIntro";
import Link from "next/link";

import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState, SectionHeading, Skeleton } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { analyticsExportUrl, buildQuery, listFields, listTopics, getAnalyticsFields } from "@/services/api";
import { extractFilters, extractPage, type SearchParams } from "@/services/filters";
import { publicationSearchHref, topicHref } from "@/services/links";

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
  const rawLevel = typeof params.level === "string" ? params.level : "field";
  const level: Level = LEVELS.some((option) => option.value === rawLevel)
    ? (rawLevel as Level)
    : "field";
  const fieldsPage = extractPage(params, "fields_page");
  const topicsPage = extractPage(params, "topics_page");

  const [fields, topics, filterFields] = await Promise.all([
    listFields({ ...filters, level, page: fieldsPage, page_size: 25 }),
    listTopics({ ...filters, page: topicsPage, page_size: 25 }),
    getAnalyticsFields({ limit: 100 }),
  ]);

  return (
    <div className="flex flex-col gap-5">
      <PageIntro title="Follow the AI ideas." description="Explore the fields and topics represented within Sri Lanka’s AI-related publications." />

      <AnalyticsFilters params={params} basePath="/topics" fields={filterFields.ok ? filterFields.value.data.map(f => f.label) : []} />
      <div className="panel p-3">
        <p className="flex gap-2 text-body-sm text-ink-secondary">
          <span aria-hidden className="text-muted">
            ⓘ
          </span>
          <span>
            Topics and fields come from source and index classification
            (OpenAlex), not an official national research taxonomy. They are
            automated assignments and carry the usual misclassification risk.
          </span>
        </p>
      </div>

      <section>
        <SectionHeading
          title="Classification breakdown"
          description="Publication counts at the selected level of the classification hierarchy."
          action={
            <nav aria-label="Classification level">
              <ul className="flex gap-1">
                {LEVELS.map((option) => (
                  <li key={option.value}>
                    <Link
                      href={`/topics${buildQuery({ ...filters, level: option.value })}`}
                      aria-current={option.value === level ? "true" : undefined}
                      className={`inline-block rounded-md border px-2.5 py-1 text-body-sm ${
                        option.value === level
                          ? "border-primary font-medium text-primary"
                          : "border-rule text-ink-secondary hover:bg-wash"
                      }`}
                    >
                      {option.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>
          }
        />

        {!fields.ok ? (
          <ApiErrorPanel error={fields.error} what="the field breakdown" />
        ) : fields.value.data.length === 0 ? (
          <EmptyState title="No classification data available" />
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
            <DistributionChart entries={fields.value.data.map(entry => ({ label: entry.label, value: entry.publication_count }))} initialView="mosaic" ariaLabel={`AI publication distribution by ${level}`} />
            <p className="mt-3 text-xs text-muted">Distribution covers the current directory page. Topics can overlap; counts are assignments, not distinct-publication shares.</p>
          </ChartPanel>
        )}
      </section>

      {level === "field" && fields.ok ? <Suspense fallback={<Skeleton className="h-80" />}><ActivityPanel filters={filters} fields={fields.value.data.map(f => f.label)} /></Suspense> : null}

      <section>
        <SectionHeading
          title="Topics"
          description="Fine-grained topic assignments, ranked by publication count."
        />
        {!topics.ok ? (
          <ApiErrorPanel error={topics.error} what="the topic directory" />
        ) : topics.value.data.length === 0 ? (
          <EmptyState title="No topics available" />
        ) : (
          <>
            <div className="panel p-1">
              <RankingTable
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
