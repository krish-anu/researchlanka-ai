import Link from "next/link";

import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { ChartPanel, DownloadLink } from "@/components/ui/ChartPanel";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { RankingTable } from "@/components/ui/RankingTable";
import { SnapshotNote } from "@/components/ui/Provenance";
import { analyticsExportUrl, listFields, listTopics } from "@/services/api";
import { extractFilters, type SearchParams } from "@/services/filters";
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

  const [fields, topics] = await Promise.all([
    listFields({ ...filters, level, limit: 40 }),
    listTopics({ ...filters, limit: 60 }),
  ]);

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h1 className="text-2xl font-semibold text-ink">Topics and fields</h1>
        <p className="mt-1 max-w-prose text-sm text-ink-secondary">
          Where national research output concentrates. Short bars are the
          under-represented areas — useful for spotting gaps as well as
          strengths.
        </p>
      </div>

      <div className="panel p-3">
        <p className="flex gap-2 text-sm text-ink-secondary">
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
                      href={`/topics?level=${option.value}`}
                      aria-current={option.value === level ? "true" : undefined}
                      className={`inline-block rounded-md border px-2.5 py-1 text-sm ${
                        option.value === level
                          ? "border-series-1 font-medium text-series-1"
                          : "border-hairline text-ink-secondary hover:bg-wash"
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
            action={<DownloadLink href={analyticsExportUrl("fields")} />}
            table={
              <details className="mt-3 border-t border-hairline pt-3">
                <summary className="cursor-pointer text-sm text-ink-secondary hover:text-ink">
                  View as table
                </summary>
                <div className="mt-2">
                  <RankingTable
                    entries={fields.value.data}
                    labelHeader={level}
                    href={(label) =>
                      publicationSearchHref(
                        level === "subfield"
                          ? { subfield: label }
                          : { field: label },
                      )
                    }
                  />
                </div>
              </details>
            }
          >
            <RankingBarChart
              entries={fields.value.data.slice(0, 20).map((entry) => ({
                label: entry.label,
                value: entry.publication_count,
              }))}
              valueLabel="Publications"
              ariaLabel={`Bar chart of publications by ${level}`}
            />
          </ChartPanel>
        )}
      </section>

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
          <div className="panel p-1">
            <RankingTable
              entries={topics.value.data}
              labelHeader="Topic"
              href={topicHref}
            />
          </div>
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
