import Link from "next/link";

import { PipelineRunPanel } from "@/components/admin/PipelineRunPanel";
import { RoleBadge } from "@/components/auth/RoleBadge";
import { ApiErrorPanel, SectionHeading } from "@/components/ui/Feedback";
import { DataTable, type Column } from "@/components/ui/DataTable";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { getDataQuality, getDatasetMeta, getHealth } from "@/services/api";
import { getSessionUser } from "@/services/auth/server";
import { listUsers } from "@/services/auth/store";
import { formatDate, formatDateTime, formatNumber, formatPercent } from "@/services/format";
import { RetryButton } from "@/components/ui/RetryButton";
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

  const session = await getSessionUser();
  const checkedAt = new Date().toISOString();
  const apiUp =
    health.ok &&
    (health.value.data.status === "ok" || health.value.data.status === "healthy");
  const admins = users.filter((user) => user.role === "admin").length;
  const suspended = users.filter((user) => user.disabled).length;

  return (
    <div className="flex flex-col gap-6">
      <SectionHeading
        level={1}
        title="Overview"
        description="Ingestion health, quality, and the queues that need a person."
      />
      <div
        role="status"
        className={`flex flex-wrap items-center justify-between gap-3 rounded-lg border px-4 py-3 ${
          apiUp
            ? "border-rule bg-wash"
            : "border-critical/40 bg-critical/5"
        }`}
      >
        <div className="flex items-center gap-3">
          <span
            aria-hidden
            className={`inline-block h-2.5 w-2.5 rounded-full ${
              apiUp ? "bg-success-text" : "bg-critical"
            }`}
          />
          <div>
            <p className="text-body-sm font-medium text-ink">
              Analytics API {apiUp ? "reachable" : "unreachable"}
            </p>
            <p className="text-body-sm text-ink-secondary">
              {apiUp
                ? `Contract ${health.value.data.api_version} · Updated at ${formatDateTime(checkedAt)}`
                : health.ok
                  ? `Updated at ${formatDateTime(checkedAt)} · service reported ${health.value.data.status}`
                  : `Unreachable · stale since ${formatDateTime(checkedAt)}. Queue and account tools still work.`}
            </p>
            <p className="text-body-sm text-ink-secondary">
              Last load{" "}
              {formatDate(meta.ok ? meta.value.data.max_loaded_at ?? null : null)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {session ? <RoleBadge role={session.role} /> : null}
          {!apiUp ? (
          <span className="flex flex-wrap items-center gap-3">
            <RetryButton variant="secondary" />
            <Link
              href="/admin/pipeline"
              className="text-body-sm font-medium text-primary underline"
            >
              Open pipeline
            </Link>
          </span>
          ) : null}
        </div>
      </div>

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
          <div className="panel flex flex-wrap items-center justify-between gap-3 p-4 text-body-sm text-ink-secondary">
            <p>
              Monitoring metrics are unavailable. Configure the backend admin API
              token to read production health counters, then retry.
            </p>
            <RetryButton variant="secondary" />
          </div>
        )}
      </section>

      <section>
        <SectionHeading
          title="Needs attention"
          description="Queues owned by this application. Decisions taken here are recorded and applied on the next pipeline run."
        />
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
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
      className="panel interactive-card flex flex-col gap-2 p-3"
    >
      <span className="label-caps text-muted">{label}</span>
      <span className="font-display text-h2 tabular text-ink">
        {formatNumber(count)}
      </span>
      <span className="text-body-sm text-ink-secondary">{caption}</span>
      <span className="mt-auto pt-2 text-body-sm font-medium text-primary">
        Open queue →
      </span>
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
    safeAdminData("audit log", () => listAudit(5), [] as AuditEntry[]),
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
  const ml = metrics.ml_monitoring ?? drift.ml_monitoring;
  const activeAlerts = ml?.active_alerts ?? [];
  const model = metrics.model_contract;
  const evaluation = model?.evaluation;

  return (
    <div className="flex flex-col gap-4">
      {activeAlerts.length > 0 ? (
        <div className="panel border-amber-500/40 bg-amber-500/5 p-4 dark:border-amber-500/30 dark:bg-amber-950/20">
          <div className="flex items-center gap-2">
            <span className="text-h3">⚠</span>
            <p className="font-semibold text-amber-700 dark:text-amber-400">
              Active ML Pipeline Drift Alerts ({activeAlerts.length})
            </p>
          </div>
          <ul className="mt-2 space-y-1 pl-6 list-disc text-body-sm text-ink-secondary">
            {activeAlerts.map((alert, idx) => (
              <li key={idx} className="font-medium">
                {alert.message}
              </li>
            ))}
          </ul>
        </div>
      ) : drift.alert ? (
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
          label="Loaded AI share"
          value={formatPercent(metrics.ai_acceptance_rate)}
          caption="AI rows in the loaded binary dataset"
        />
        <StatTile
          label="Loaded AI rate"
          value={formatPercent(metrics.auto_ai_rate)}
          caption="accepted AI rows from loaded data"
        />
        <StatTile
          label="Loaded NON_AI rate"
          value={formatPercent(metrics.auto_non_ai_rate)}
          caption="non-AI rows from loaded data"
        />
        <StatTile
          label="Holdout FP"
          value={
            evaluation?.test_false_positives == null
              ? "—"
              : formatNumber(evaluation.test_false_positives)
          }
          caption="frozen human holdout false positives"
        />
        <StatTile
          label="Holdout macro F1"
          value={
            evaluation?.test_macro_f1 == null
              ? "—"
              : evaluation.test_macro_f1.toFixed(3)
          }
          caption="trained model evaluation, not workflow"
        />
        <StatTile
          label="Holdout precision"
          value={
            evaluation?.test_ai_precision == null
              ? "—"
              : formatPercent(evaluation.test_ai_precision * 100)
          }
          caption="AI precision on frozen holdout"
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
          value={model?.model_id ?? metrics.model_version ?? "—"}
          caption={
            model
              ? `${model.model_type} · ${model.features.join(", ")}`
              : "latest public classifier version"
          }
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

      {ml ? <RealMLMonitoringSection ml={ml} /> : null}

      <div className="panel p-4">
        <h3 className="font-display text-h3 text-ink">Monthly auto AI drift</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <DriftCard label="Previous month" month={drift.previous_month} />
          <DriftCard label="Current month" month={drift.current_month} />
        </div>
      </div>
    </div>
  );
}

function RealMLMonitoringSection({ ml }: { ml: NonNullable<MonitoringMetrics["ml_monitoring"]> }) {
  return (
    <div className="panel flex flex-col gap-4 p-4">
      <div className="flex flex-col justify-between gap-1 sm:flex-row sm:items-center">
        <div>
          <h3 className="font-display text-h3 text-ink">Real ML Monitoring (7 Drift Dimensions)</h3>
          <p className="text-body-sm text-ink-secondary">
            Comparing <strong className="text-ink">{ml.previous_period ?? "Baseline"}</strong> with{" "}
            <strong className="text-ink">{ml.current_period ?? "Current"}</strong> (Cohort basis: {ml.date_basis})
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-caption font-semibold ${
            ml.overall_alert
              ? "bg-amber-500/10 text-amber-700 dark:text-amber-400 border border-amber-500/30"
              : "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/30"
          }`}
        >
          {ml.overall_alert ? "⚠ Drift Alerts Active" : "✓ All Dimensions Stable"}
        </span>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {/* 1. Confidence Drift */}
        <div className="rounded-md border border-rule p-3 bg-canvas-subtle/50 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="label-caps text-muted">Confidence Drift (P(AI))</span>
              {ml.confidence_drift.alert ? (
                <span className="text-caption font-bold text-amber-600">⚠ Drift</span>
              ) : (
                <span className="text-caption text-emerald-600">Stable</span>
              )}
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <p className="font-display text-h2 text-ink">
                {ml.confidence_drift.current_mean_p_ai.toFixed(2)}
              </p>
              <span className="text-body-sm font-medium text-ink-secondary">
                from {ml.confidence_drift.previous_mean_p_ai.toFixed(2)} (
                <span className={ml.confidence_drift.mean_p_ai_delta > 0 ? "text-amber-600 font-semibold" : ""}>
                  {ml.confidence_drift.mean_p_ai_delta > 0 ? "+" : ""}
                  {ml.confidence_drift.mean_p_ai_delta.toFixed(2)}
                </span>
                )
              </span>
            </div>
            <p className="mt-1 text-caption text-ink-secondary">
              Median: {ml.confidence_drift.current_median_p_ai.toFixed(2)} · High confidence share:{" "}
              {formatPercent(ml.confidence_drift.bins.high.current_pct)}
            </p>
          </div>
        </div>

        {/* 2. Prediction Drift */}
        <div className="rounded-md border border-rule p-3 bg-canvas-subtle/50 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="label-caps text-muted">Prediction Drift</span>
              {ml.prediction_drift.alert ? (
                <span className="text-caption font-bold text-amber-600">⚠ Shift</span>
              ) : (
                <span className="text-caption text-emerald-600">Stable</span>
              )}
            </div>
            <div className="mt-2 flex items-baseline gap-2">
              <p className="font-display text-h2 text-ink">
                {formatPercent(ml.prediction_drift.current_ai_rate)}
              </p>
              <span className="text-body-sm font-medium text-ink-secondary">
                AI rate (
                <span className={Math.abs(ml.prediction_drift.ai_rate_delta_points) >= 15 ? "text-amber-600 font-semibold" : ""}>
                  {ml.prediction_drift.ai_rate_delta_points > 0 ? "+" : ""}
                  {ml.prediction_drift.ai_rate_delta_points.toFixed(1)} pts
                </span>
                )
              </span>
            </div>
            <p className="mt-1 text-caption text-ink-secondary">
              PSI score: <span className="font-semibold text-ink">{ml.prediction_drift.psi_score.toFixed(4)}</span> · Non-AI:{" "}
              {formatPercent(ml.prediction_drift.current_non_ai_rate)}
            </p>
          </div>
        </div>

        {/* 3. Source Drift */}
        <div className="rounded-md border border-rule p-3 bg-canvas-subtle/50 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="label-caps text-muted">Source Drift</span>
              {ml.source_drift.alert ? (
                <span className="text-caption font-bold text-amber-600">⚠ Imbalance</span>
              ) : (
                <span className="text-caption text-emerald-600">Stable</span>
              )}
            </div>
            <div className="mt-2 space-y-1">
              {ml.source_drift.sources.map((src) => (
                <div key={src.name} className="flex justify-between text-body-sm">
                  <span className="text-ink-secondary">{src.name}</span>
                  <span className={`font-medium ${src.alert ? "text-amber-600 font-bold" : "text-ink"}`}>
                    {src.current_pct.toFixed(1)}%{" "}
                    <span className="text-caption text-muted">
                      ({src.delta_points > 0 ? "+" : ""}
                      {src.delta_points.toFixed(1)})
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 4. Feature Drift */}
        <div className="rounded-md border border-rule p-3 bg-canvas-subtle/50 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="label-caps text-muted">Feature Drift</span>
              {ml.feature_drift.alert ? (
                <span className="text-caption font-bold text-amber-600">⚠ Diverged</span>
              ) : (
                <span className="text-caption text-emerald-600">Stable</span>
              )}
            </div>
            <p className="mt-2 font-display text-h2 text-ink">
              {ml.feature_drift.current_avg_title_words} <span className="text-body-sm font-normal text-muted">words/title</span>
            </p>
            <p className="mt-1 text-caption text-ink-secondary">
              Abstract words: {ml.feature_drift.current_avg_abstract_words} · Abstract presence:{" "}
              {formatPercent(ml.feature_drift.current_abstract_presence_pct)}
            </p>
          </div>
        </div>

        {/* 5. Missing Data Drift */}
        <div className="rounded-md border border-rule p-3 bg-canvas-subtle/50 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="label-caps text-muted">Missing-Data Drift</span>
              {ml.missing_data_drift.alert ? (
                <span className="text-caption font-bold text-amber-600">⚠ Surge</span>
              ) : (
                <span className="text-caption text-emerald-600">Stable</span>
              )}
            </div>
            <div className="mt-2 space-y-1">
              {Object.entries(ml.missing_data_drift.fields).map(([k, item]) => (
                <div key={k} className="flex justify-between text-body-sm">
                  <span className="text-ink-secondary">{item.label}</span>
                  <span className={`font-medium ${item.alert ? "text-amber-600 font-bold" : "text-ink"}`}>
                    {item.current_pct.toFixed(1)}%{" "}
                    <span className="text-caption text-muted">
                      ({item.delta_points > 0 ? "+" : ""}
                      {item.delta_points.toFixed(1)})
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 6. Institution Drift */}
        <div className="rounded-md border border-rule p-3 bg-canvas-subtle/50 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="label-caps text-muted">Institution Drift</span>
              {ml.institution_drift.alert ? (
                <span className="text-caption font-bold text-amber-600">⚠ Skewed</span>
              ) : (
                <span className="text-caption text-emerald-600">Stable</span>
              )}
            </div>
            <p className="mt-2 text-caption text-ink-secondary">
              Top 3 Concentration:{" "}
              <strong className="text-ink">
                {formatPercent(ml.institution_drift.top3_concentration_current_pct)}
              </strong>
            </p>
            <div className="mt-1 space-y-0.5">
              {ml.institution_drift.top_institutions.slice(0, 3).map((inst) => (
                <div key={inst.institution} className="truncate text-caption text-ink-secondary">
                  · {inst.institution} ({inst.current_share_pct.toFixed(1)}%)
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* 7. Human Disagreement Drift */}
        <div className="rounded-md border border-rule p-3 bg-canvas-subtle/50 flex flex-col justify-between sm:col-span-2 lg:col-span-3">
          <div className="flex items-center justify-between">
            <span className="label-caps text-muted">Human Disagreement & Overturn Drift</span>
            {ml.human_disagreement_drift.alert ? (
              <span className="text-caption font-bold text-amber-600">⚠ High Overturns</span>
            ) : (
              <span className="text-caption text-emerald-600">Stable</span>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-6">
            <div>
              <p className="text-caption text-muted">Disagreement Rate</p>
              <p className="font-display text-h3 text-ink">
                {formatPercent(ml.human_disagreement_drift.current_disagreement_rate)}
              </p>
            </div>
            <div>
              <p className="text-caption text-muted">Human Decisions</p>
              <p className="font-display text-h3 text-ink">
                {formatNumber(ml.human_disagreement_drift.current_human_decisions)}
              </p>
            </div>
            <div>
              <p className="text-caption text-muted">False Positive Overturns</p>
              <p className="font-display text-h3 text-ink">
                {formatNumber(ml.human_disagreement_drift.current_fp_overturns)}
              </p>
            </div>
            <div>
              <p className="text-caption text-muted">False Negative Overturns</p>
              <p className="font-display text-h3 text-ink">
                {formatNumber(ml.human_disagreement_drift.current_fn_overturns)}
              </p>
            </div>
          </div>
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
