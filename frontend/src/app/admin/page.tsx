import Link from "next/link";

import { PipelineRunPanel } from "@/components/admin/PipelineRunPanel";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { getDataQuality, getDatasetMeta, getHealth } from "@/services/api";
import { listUsers } from "@/services/auth/store";
import { formatDate, formatNumber, formatPercent } from "@/services/format";
import {
  readIncrementalJobStatus,
  type IncrementalJobStatus,
} from "@/services/admin/incremental";
import {
  readMonitoringMetrics,
  type MonitoringMetrics,
} from "@/services/admin/monitoring";
import { countPendingAIReviewCandidates } from "@/services/workspace/aiReview";
import { countPendingCandidates } from "@/services/workspace/resolution";
import { countOpenFlags, listAudit } from "@/services/workspace/store";
import type { UserRecord } from "@/types/auth";
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
  const {
    health,
    meta,
    quality,
    users,
    openFlags,
    pendingCandidates,
    pendingAIReview,
    audit,
    incrementalStatus,
    monitoring,
  } = await loadAdminOverviewData();

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
          title="AI update"
          description="Manual incremental collection and AI-only database loading."
        />
        <PipelineRunPanel
          status={incrementalStatus}
        />
      </section>

      <section>
        <SectionHeading
          title="Monitoring"
          description="Operational health for the public AI corpus, review workflow, ingestion, and model drift."
        />
        {monitoring ? (
          <MonitoringPanel metrics={monitoring} />
        ) : (
          <div className="panel p-4 text-body-sm text-ink-secondary">
            Monitoring metrics are unavailable. Configure the backend admin API
            token to read production health counters.
          </div>
        )}
      </section>

      <section>
        <SectionHeading
          title="Needs attention"
          description="Queues owned by this application. Decisions taken here are recorded and applied on the next pipeline run."
        />
        <div className="grid gap-4 sm:grid-cols-3">
          <QueueCard
            href="/admin/ai-review"
            label="AI review"
            count={pendingAIReview}
            caption="AI REVIEW predictions awaiting a final label"
          />
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

const IDLE_INCREMENTAL_STATUS: IncrementalJobStatus = {
  status: "idle",
  message: "No incremental AI update has been started from this console.",
  db_labels: ["AI"],
};

async function safeAdminData<T>(
  label: string,
  read: () => Promise<T>,
  fallback: T,
): Promise<T> {
  try {
    return await read();
  } catch (error) {
    console.warn(`[admin] Could not read ${label}`, error);
    return fallback;
  }
}

async function loadAdminOverviewData() {
  const [
    health,
    meta,
    quality,
    users,
    openFlags,
    pendingCandidates,
    pendingAIReview,
    audit,
    incrementalStatus,
    monitoring,
  ] = await Promise.all([
    getHealth(),
    getDatasetMeta(),
    getDataQuality({ group_by: "source_dataset" }),
    safeAdminData("users", listUsers, [] as UserRecord[]),
    safeAdminData("open flags", countOpenFlags, 0),
    safeAdminData("resolution candidates", countPendingCandidates, 0),
    safeAdminData("AI review candidates", countPendingAIReviewCandidates, 0),
    safeAdminData("audit log", () => listAudit(8), [] as AuditEntry[]),
    safeAdminData(
      "incremental update status",
      readIncrementalJobStatus,
      IDLE_INCREMENTAL_STATUS,
    ),
    safeAdminData("monitoring metrics", readMonitoringMetrics, null),
  ]);

  return {
    health,
    meta,
    quality,
    users,
    openFlags,
    pendingCandidates,
    pendingAIReview,
    audit,
    incrementalStatus,
    monitoring,
  };
}

function MonitoringPanel({ metrics }: { metrics: MonitoringMetrics }) {
  const drift = metrics.drift;
  return (
    <div className="flex flex-col gap-4">
      {drift.alert ? (
        <div className="panel border-serious/50 bg-wash p-4">
          <p className="font-medium text-serious">AI classification drift alert</p>
          <p className="mt-1 text-body-sm text-ink-secondary">
            AUTO_AI changed by{" "}
            {formatSignedPercentPoints(drift.auto_ai_rate_delta_points)} between{" "}
            {drift.previous_month?.month ?? "previous month"} and{" "}
            {drift.current_month?.month ?? "current month"}.
          </p>
        </div>
      ) : null}

      <StatTileGrid>
        <StatTile
          label="Public publications"
          value={formatNumber(metrics.public_publications)}
          caption="currently visible public corpus"
        />
        <StatTile
          label="Pending reviews"
          value={formatNumber(metrics.pending_reviews)}
          caption="AI review records awaiting humans"
        />
        <StatTile
          label="AI acceptance rate"
          value={formatPercent(metrics.ai_acceptance_rate)}
          caption="accepted over review workflow records"
        />
        <StatTile
          label="Auto AI rate"
          value={formatPercent(metrics.auto_ai_rate)}
          caption="auto-accepted by classifier gate"
        />
        <StatTile
          label="Auto NON_AI rate"
          value={formatPercent(metrics.auto_non_ai_rate)}
          caption="system rejected as non-AI"
        />
        <StatTile
          label="False positive rate"
          value={formatPercent(metrics.false_positive_rate)}
          caption={metrics.metric_notes.false_positive_rate}
        />
        <StatTile
          label="Human disagreement"
          value={formatPercent(metrics.human_disagreement_rate)}
          caption="human rejections over human decisions"
        />
        <StatTile
          label="Collected/day"
          value={formatNumber(metrics.publications_collected_per_day)}
          caption="average loaded days in last 30 days"
        />
        <StatTile
          label="Failed jobs"
          value={formatNumber(metrics.failed_ingestion_jobs)}
          caption="incremental pipeline failures"
        />
        <StatTile
          label="Duplicate rate"
          value={formatPercent(metrics.duplicate_rate)}
          caption={metrics.metric_notes.duplicate_rate}
        />
        <StatTile
          label="Missing abstract"
          value={formatPercent(metrics.missing_abstract_percentage)}
          caption="public corpus"
        />
        <StatTile
          label="Missing DOI"
          value={formatPercent(metrics.missing_doi_percentage)}
          caption="public corpus"
        />
        <StatTile
          label="Ownership review"
          value={formatNumber(metrics.ownership_review_count)}
          caption="ownership rows still needing attention"
        />
        <StatTile
          label="Model version"
          value={metrics.model_version ?? "—"}
          caption="latest public classifier version"
        />
        <StatTile
          label="Dataset version"
          value={metrics.dataset_version ?? "—"}
          caption={metrics.pipeline_version ?? "pipeline version unavailable"}
        />
        <StatTile
          label="Last successful run"
          value={formatDate(metrics.last_successful_pipeline_run)}
          caption="incremental pipeline"
        />
      </StatTileGrid>

      <div className="panel p-4">
        <h3 className="font-display text-h3 text-ink">Drift monitoring</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <DriftCard label="Previous month" month={drift.previous_month} />
          <DriftCard label="Current month" month={drift.current_month} />
        </div>
      </div>
    </div>
  );
}

function DriftCard({ label, month }: { label: string; month: MonitoringMetrics["drift"]["current_month"] }) {
  return (
    <div className="rounded-md border border-rule p-3">
      <p className="label-caps text-muted">{label}</p>
      <p className="mt-1 font-display text-h2 text-ink">
        {month ? formatPercent(month.auto_ai_rate) : "—"}
      </p>
      <p className="text-body-sm text-ink-secondary">
        {month ? `${month.month} · ${formatNumber(month.auto_ai_count)} AUTO_AI of ${formatNumber(month.total)}` : "No data"}
      </p>
    </div>
  );
}

function formatSignedPercentPoints(value: number | null): string {
  if (value === null) return "—";
  const prefix = value > 0 ? "+" : "";
  return `${prefix}${value.toFixed(1)} percentage points`;
}
