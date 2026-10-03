import { formatNumber } from "@/services/format";

export type IncrementalRunStatus =
  | "idle"
  | "queued"
  | "running"
  | "succeeded"
  | "failed";

export interface IncrementalRunSnapshot {
  status: IncrementalRunStatus | string;
  fromDate?: string | null;
  toDate?: string | null;
  reviewThreshold?: number | string | null;
  startedAt?: string | null;
  finishedAt?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  collected?: number | null;
  selected?: number | null;
  newRecords?: number | null;
  updatedRecords?: number | null;
  loaded?: number | null;
  message: string;
  /** Phase the pipeline last reported. Absent until a run publishes one. */
  step?: string | null;
  error?: string | null;
  logPath?: string | null;
  log_path?: string | null;
  result?: IncrementalRunResult | null;
  db_labels?: string[];
}

export interface IncrementalRunResult {
  from_date?: string | null;
  to_date?: string | null;
  csv_output?: string | null;
  db_load_output?: string | null;
  records_collected?: number | null;
  records_selected_for_db?: number | null;
  records_new_for_db?: number | null;
  records_updated_for_db?: number | null;
  records_loaded?: number | null;
}

type StageState = "completed" | "current" | "remaining" | "failed";

interface Stage {
  id: string;
  label: string;
  detail: string;
  state: StageState;
}

const FLOW: { id: string; label: string; detail: string }[] = [
  { id: "window", label: "Date window", detail: "Resolve the manual or monthly range." },
  { id: "fetch", label: "Fetch records", detail: "Collect publications for that range." },
  { id: "classify", label: "Classify", detail: "Score AI relevance." },
  { id: "prepare", label: "Load file", detail: "Write the rows the database will take." },
  { id: "load", label: "Database", detail: "Insert new rows and update matches." },
  { id: "checkpoint", label: "Checkpoint", detail: "Save the run so the next update continues." },
];

const FLOW_LABELS = {
  completed: "Completed",
  current: "In progress",
  remaining: "Remaining",
  failed: "Needs attention",
} satisfies Record<StageState, string>;

export function IncrementalUpdateDiagram({
  run,
}: {
  run: IncrementalRunSnapshot;
}) {
  const stages = buildStages(run);
  const completed = stages.filter((stage) => stage.state === "completed").length;
  const failed = stages.some((stage) => stage.state === "failed");
  const progress = failed ? completed : Math.round((completed / stages.length) * 100);

  return (
    <div className="panel">
      <div className="border-b border-rule bg-wash px-5 py-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="label-caps text-machine">AI update flow</p>
            <h3 className="mt-1 font-display text-h3 text-ink">
              Manual and monthly dataset update
            </h3>
          </div>
          <div className="flex flex-wrap gap-2 text-body-sm">
            <StatusPill status={run.status} />
            {run.reviewThreshold ? (
              <span className="rounded border border-rule bg-surface px-3 py-1 text-ink-secondary">
                threshold {run.reviewThreshold}
              </span>
            ) : null}
          </div>
        </div>
        <div
          className="mt-4 h-2 overflow-hidden rounded bg-sunk"
          role="progressbar"
          aria-label="Incremental update progress"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress}
        >
          <div
            className={`h-full ${failed ? "bg-serious" : "bg-primary"}`}
            style={{ width: `${progress}%` }}
          />
        </div>
      </div>

      {run.status === "failed" && (run.error || run.message) ? (
        <div className="border-b border-rule bg-surface px-5 py-4">
          <p className="label-caps text-serious">Failure reason</p>
          <p className="mt-2 text-body-sm text-ink-secondary">
            {shortError(run.error ?? run.message)}
          </p>
        </div>
      ) : null}

      <ol className="flex flex-col px-3 py-4 lg:flex-row lg:items-stretch">
        {stages.map((stage, index) => (
          <li key={stage.id} className="flex min-w-0 flex-1 flex-col lg:flex-row lg:items-center">
            <div
              title={stage.detail}
              className={`flex min-h-[5.5rem] w-full flex-col gap-1 rounded-lg border px-3 py-3 ${stageClassName(stage.state)}`}
            >
              <span className="label-caps text-muted">{index + 1}</span>
              <h4 className="font-display text-body-sm font-semibold text-ink">{stage.label}</h4>
              <span className={`mt-auto self-start ${stateBadgeClassName(stage.state)}`}>
                {FLOW_LABELS[stage.state]}
              </span>
            </div>
            {index < stages.length - 1 ? (
              <FlowArrow state={stage.state} />
            ) : null}
          </li>
        ))}
      </ol>

      <dl className="grid grid-cols-2 gap-px border-t border-rule bg-rule sm:grid-cols-5">
        <Metric label="Collected" value={run.collected} />
        <Metric label="Selected as AI" value={run.selected} />
        <Metric label="New records" value={run.newRecords ?? run.result?.records_new_for_db} />
        <Metric label="Updated records" value={run.updatedRecords ?? run.result?.records_updated_for_db} />
        <Metric label="Loaded / updated" value={run.loaded} />
      </dl>
    </div>
  );
}

function buildStages(run: IncrementalRunSnapshot): Stage[] {
  const status = String(run.status || "idle").toLowerCase();
  const reported = FLOW.findIndex((stage) => stage.id === run.step);

  return FLOW.map((stage, index) => ({
    ...stage,
    state: stageStateFor(index, reported, status),
  }));
}

function stageStateFor(index: number, reported: number, status: string): StageState {
  if (status === "succeeded") return "completed";
  if (status === "failed") {
    if (reported < 0) return "remaining";
    if (index < reported) return "completed";
    if (index === reported) return "failed";
    return "remaining";
  }
  if (status === "running" || status === "queued") {
    const active = reported < 0 ? 0 : reported;
    if (index < active) return "completed";
    if (index === active) return "current";
    return "remaining";
  }
  return "remaining";
}

function FlowArrow({ state }: { state: StageState }) {
  const tone =
    state === "failed"
      ? "text-serious"
      : state === "completed" || state === "current"
        ? "text-primary"
        : "text-muted";

  return (
    <span
      aria-hidden
      className={`flex shrink-0 items-center justify-center py-1 lg:px-1 lg:py-0 ${tone}`}
    >
      <svg viewBox="0 0 24 24" className="size-4 rotate-90 lg:rotate-0" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
        <path d="M4 12h14" />
        <path d="M14 6l6 6-6 6" />
      </svg>
    </span>
  );
}

function StatusPill({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  const className =
    normalized === "succeeded"
      ? "border-good bg-surface text-good"
      : normalized === "failed"
        ? "border-serious bg-surface text-serious"
        : normalized === "running"
          ? "border-machine bg-machine-container text-machine"
          : "border-rule bg-surface text-ink-secondary";

  return (
    <span className={`label-caps rounded border px-3 py-1 ${className}`}>
      {status}
    </span>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: number | null | undefined;
}) {
  return (
    <div className="bg-surface px-4 py-3">
      <dt className="label-caps text-muted">{label}</dt>
      <dd className="mt-1 font-display text-h2 tabular text-ink">
        {typeof value === "number" ? formatNumber(value) : "—"}
      </dd>
    </div>
  );
}

function stageClassName(state: StageState): string {
  if (state === "current") {
    return "relative z-10 -translate-y-1 border-primary bg-surface shadow-md";
  }
  if (state === "completed") return "border-rule bg-surface";
  if (state === "failed") return "border-serious bg-surface";
  return "border-rule bg-wash";
}

function stateBadgeClassName(state: StageState): string {
  const base = "rounded border px-2 py-1 text-label font-bold uppercase";
  if (state === "completed") return `${base} border-good text-good`;
  if (state === "current") return `${base} border-machine text-machine`;
  if (state === "failed") return `${base} border-serious text-serious`;
  return `${base} border-rule text-muted`;
}

function shortError(value: string | null | undefined): string {
  if (!value) return "";
  const lines = value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.at(-1) ?? value.trim();
}
