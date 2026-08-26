import Link from "next/link";

import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { getDataQuality, getDatasetMeta, getHealth } from "@/services/api";
import { listUsers } from "@/services/auth/store";
import { formatDate, formatNumber, formatPercent } from "@/services/format";
import { countPendingCandidates } from "@/services/workspace/resolution";
import { countOpenFlags, listAudit } from "@/services/workspace/store";
import type { AuditEntry } from "@/services/workspace/types";

export const metadata = { title: "Overview" };

/**
 * Console home.
 *
 * Two kinds of figure sit side by side here and the layout keeps them apart:
 * the corpus numbers on the left come from the read-only analytics API and
 * describe the pipeline's output, while the queue counts and account totals on
 * the right are this app's own state. Mixing them into one strip would imply
 * the platform can change the corpus from this screen, which it cannot.
 */
export default async function AdminOverviewPage() {
  const [health, meta, quality, users, openFlags, pendingCandidates, audit] =
    await Promise.all([
      getHealth(),
      getDatasetMeta(),
      getDataQuality({ group_by: "source_dataset" }),
      listUsers(),
      countOpenFlags(),
      countPendingCandidates(),
      listAudit(8),
    ]);

  const apiUp = health.ok && health.value.data.status === "ok";
  const admins = users.filter((user) => user.role === "admin").length;
  const suspended = users.filter((user) => user.disabled).length;

  return (
    <div className="flex flex-col gap-8">
      <section>
        <SectionHeading
          title="Corpus"
          description="Live figures from the read-only analytics API. These describe the pipeline's output and are not editable from this console."
        />
        {!meta.ok ? (
          <ApiErrorPanel error={meta.error} what="the dataset summary" />
        ) : (
          <StatTileGrid>
            <StatTile
              label="API"
              value={apiUp ? "Healthy" : "Unavailable"}
              caption={
                health.ok
                  ? `contract ${health.value.data.api_version}`
                  : "no response from the service"
              }
            />
            <StatTile
              label="Records"
              value={formatNumber(meta.value.data.publication_count ?? null)}
              caption={meta.value.data.dataset_stage}
            />
            <StatTile
              label="Year coverage"
              value={
                meta.value.data.min_publication_year &&
                meta.value.data.max_publication_year
                  ? `${meta.value.data.min_publication_year}–${meta.value.data.max_publication_year}`
                  : "—"
              }
              caption="earliest to latest publication year"
            />
            <StatTile
              label="Last load"
              value={formatDate(meta.value.data.max_loaded_at ?? null)}
              caption="most recent record written by the pipeline"
            />
          </StatTileGrid>
        )}
      </section>

      <section>
        <SectionHeading
          title="Needs attention"
          description="Queues owned by this application. Decisions taken here are recorded and applied on the next pipeline run."
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <QueueCard
            href="/admin/review"
            label="Resolution queue"
            count={pendingCandidates}
            caption="duplicate candidates awaiting a human decision"
          />
          <QueueCard
            href="/admin/flags"
            label="Flag triage"
            count={openFlags}
            caption="records reported by signed-in users"
          />
          <QueueCard
            href="/admin/users"
            label="Accounts"
            count={users.length}
            caption={`${admins} administrator${admins === 1 ? "" : "s"}${
              suspended > 0 ? ` · ${suspended} suspended` : ""
            }`}
          />
        </div>
      </section>

      <section>
        <SectionHeading
          title="Data quality"
          description="Missingness across the consolidated corpus, from /analytics/data-quality."
          action={
            <Link
              href="/admin/pipeline"
              className="text-body-sm text-primary underline"
            >
              Per-source breakdown
            </Link>
          }
        />
        {!quality.ok ? (
          <ApiErrorPanel error={quality.error} what="the quality summary" />
        ) : (
          <StatTileGrid>
            <StatTile
              label="Missing DOI"
              value={formatPercent(quality.value.data.missing_doi_percentage)}
              caption={`of ${formatNumber(quality.value.data.record_count)} records`}
            />
            <StatTile
              label="Missing abstract"
              value={formatPercent(
                quality.value.data.missing_abstract_percentage,
              )}
              caption="abstract text absent"
            />
            <StatTile
              label="Missing institutions"
              value={formatPercent(
                quality.value.data.missing_institutions_percentage,
              )}
              caption="no affiliation resolved"
            />
            <StatTile
              label="Citation conflicts"
              value={formatNumber(quality.value.data.citation_divergence_count)}
              caption="sources disagree on the count"
            />
          </StatTileGrid>
        )}
      </section>

      <section>
        <SectionHeading
          title="Recent administrator activity"
          description="Every triage, merge and role change, newest first."
        />
        <div className="panel p-2">
          <DataTable<AuditEntry>
            rows={audit}
            rowKey={(entry) => entry.id}
            emptyMessage="No administrator actions recorded yet."
            columns={AUDIT_COLUMNS}
          />
        </div>
      </section>
    </div>
  );
}

const AUDIT_COLUMNS: Column<AuditEntry>[] = [
  {
    key: "when",
    header: "When",
    render: (entry) => formatDate(entry.created_at),
  },
  {
    key: "action",
    header: "Action",
    render: (entry) => (
      <code className="data-mono rounded bg-sunk px-1 py-0.5">
        {entry.action}
      </code>
    ),
  },
  {
    key: "summary",
    header: "Detail",
    render: (entry) => <span className="text-ink">{entry.summary}</span>,
  },
  { key: "actor", header: "By", render: (entry) => entry.actor.name },
];

function QueueCard({
  href,
  label,
  count,
  caption,
}: {
  href: string;
  label: string;
  count: number;
  caption: string;
}) {
  return (
    <Link
      href={href}
      className="panel flex flex-col gap-1 p-4 transition-colors hover:border-primary"
    >
      <span className="label-caps text-muted">{label}</span>
      <span className="font-display text-h1 tabular text-primary">
        {formatNumber(count)}
      </span>
      <span className="text-body-sm text-ink-secondary">{caption}</span>
    </Link>
  );
}
