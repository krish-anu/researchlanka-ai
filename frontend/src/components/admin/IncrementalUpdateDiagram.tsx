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
  label: string;
  detail: string;
  output?: string;
  metric?: string;
  state: StageState;
}

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
    <div className="panel overflow-hidden">
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

      <ol className="grid gap-0 md:grid-cols-2 xl:grid-cols-4">
        {stages.map((stage, index) => (
          <li
            key={stage.label}
            className={`relative min-h-48 border-b border-rule p-5 md:border-r md:last:border-r-0 xl:[&:nth-child(4n)]:border-r-0 ${
              index >= 4 ? "xl:border-t" : ""
            } ${stageClassName(stage.state)}`}
          >
            <div className="flex items-start justify-between gap-3">
              <span className="label-caps text-muted">Step {index + 1}</span>
              <span className={stateBadgeClassName(stage.state)}>
                {FLOW_LABELS[stage.state]}
              </span>
            </div>
            <div className="mt-5 flex items-center gap-3">
              <span className={nodeClassName(stage.state)} aria-hidden>
                {stage.state === "completed" ? "✓" : stage.state === "failed" ? "!" : index + 1}
              </span>
              <h4 className="font-display text-body-md font-semibold text-ink">
                {stage.label}
              </h4>
            </div>
            <p className="mt-3 min-h-12 text-body-sm text-ink-secondary">
              {stage.detail}
            </p>
            {stage.output ? (
              <p className="mt-3 rounded border border-rule bg-surface px-3 py-2 text-xs text-muted">
                {stage.output}
              </p>
            ) : null}
            {stage.metric ? (
              <p className="mt-4 data-mono text-primary">{stage.metric}</p>
            ) : null}
          </li>
        ))}
      </ol>

      <div className="grid gap-0 border-t border-rule sm:grid-cols-5">
        <Metric label="Collected" value={run.collected} />
        <Metric label="Selected as AI" value={run.selected} />
        <Metric label="New records" value={run.newRecords ?? run.result?.records_new_for_db} />
        <Metric label="Updated records" value={run.updatedRecords ?? run.result?.records_updated_for_db} />
        <Metric label="Loaded / updated" value={run.loaded} />
      </div>
    </div>
  );
}

function buildStages(run: IncrementalRunSnapshot): Stage[] {
  const status = String(run.status || "idle").toLowerCase();
  const failed = status === "failed";
  const done = status === "succeeded";
  const running = status === "running" || status === "queued";
  const collected = run.collected ?? run.result?.records_collected;
  const selected = run.selected ?? run.result?.records_selected_for_db;
  const loaded = run.loaded ?? run.result?.records_loaded;
  const newRecords = run.newRecords ?? run.result?.records_new_for_db;
  const updatedRecords = run.updatedRecords ?? run.result?.records_updated_for_db;
  const logPath = run.logPath ?? run.log_path;
  const csvOutput = run.result?.csv_output;
  const dbLoadOutput = run.result?.db_load_output;

  const collectedDone = typeof collected === "number";
  const selectedDone = typeof selected === "number";
  const loadedDone = typeof loaded === "number";
  const classifiedDone = selectedDone || loadedDone || done;
  const enrichedDone = collectedDone || classifiedDone || done;
  const selectedDoneOrFinished = selectedDone || loadedDone || done;

  return [
    {
      label: "Prepare window",
      detail: dateWindow(
        run.fromDate ?? run.result?.from_date,
        run.toDate ?? run.result?.to_date,
      ),
      state: failed || done || running ? "completed" : "remaining",
    },
    {
      label: "Fetch records",
      detail: "Collect Sri Lanka publication records for the selected date window.",
      metric: metric(collected, "records collected"),
      state: stageState({ failed, done: collectedDone || done, running }),
    },
    {
      label: "Normalize and match",
      detail: "Clean DOI, OpenAlex ID and source IDs, then match incoming records to existing publications.",
      output: csvOutput ? `Collected CSV: ${csvOutput}` : undefined,
      state: stageState({
        failed,
        done: collectedDone || done,
        running: collectedDone && running,
      }),
    },
    {
      label: "Fetch abstracts/keywords",
      detail: "Before preprocessing, fill missing abstracts and keywords from fetched metadata when available.",
      state: stageState({
        failed,
        done: enrichedDone,
        running: collectedDone && running,
      }),
    },
    {
      label: "Classify AI relevance",
      detail: "Score title, abstract, keywords, topics and concepts with the configured AI relevance model.",
      metric: metric(selected, "records selected"),
      state: stageState({
        failed,
        done: classifiedDone,
        running: enrichedDone && running,
      }),
    },
    {
      label: "Prepare DB rows",
      detail: "Keep the configured DB labels and create the exact load file for PostgreSQL.",
      metric: metric(selected, "records selected"),
      output: dbLoadOutput ? `DB load CSV: ${dbLoadOutput}` : undefined,
      state: stageState({
        failed,
        done: selectedDoneOrFinished,
        running: selectedDone && running,
      }),
    },
    {
      label: "Load database",
      detail: "Insert new rows and update matching existing rows by DOI, OpenAlex ID or source ID.",
      metric: loadMetric({ loaded, newRecords, updatedRecords }),
      state: stageState({
        failed,
        done: loadedDone || done,
        running: selectedDoneOrFinished && running,
      }),
    },
    {
      label: "Save checkpoint",
      detail: logPath ? `Run log: ${logPath}` : "Write checkpoint, message and final status for the admin console.",
      state: failed ? "failed" : done ? "completed" : "remaining",
    },
  ];
}

function stageState({
  failed,
  done,
  running,
}: {
  failed: boolean;
  done: boolean;
  running: boolean;
}): StageState {
  if (failed && !done) return "failed";
  if (done) return "completed";
  if (running) return "current";
  return "remaining";
}

function dateWindow(fromDate?: string | null, toDate?: string | null): string {
  if (fromDate && toDate) return `Collecting records from ${fromDate} to ${toDate}.`;
  if (fromDate) return `Collecting records from ${fromDate}.`;
  if (toDate) return `Collecting records up to ${toDate}.`;
  return "Resolve the manual or monthly update date range.";
}

function metric(value: number | null | undefined, label: string): string | undefined {
  return typeof value === "number" ? `${formatNumber(value)} ${label}` : undefined;
}

function loadMetric({
  loaded,
  newRecords,
  updatedRecords,
}: {
  loaded: number | null | undefined;
  newRecords: number | null | undefined;
  updatedRecords: number | null | undefined;
}): string | undefined {
  if (typeof newRecords === "number" || typeof updatedRecords === "number") {
    return `${formatNumber(newRecords ?? 0)} new / ${formatNumber(updatedRecords ?? 0)} updated`;
  }
  return metric(loaded, "records loaded");
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
    <div className="border-b border-rule px-5 py-4 sm:border-b-0 sm:border-r sm:last:border-r-0">
      <dt className="label-caps text-muted">{label}</dt>
      <dd className="mt-2 font-display text-h3 text-primary">
        {typeof value === "number" ? formatNumber(value) : "-"}
      </dd>
    </div>
  );
}

function stageClassName(state: StageState): string {
  if (state === "completed") return "bg-surface";
  if (state === "current") return "bg-machine-container";
  if (state === "failed") return "bg-surface";
  return "bg-wash";
}

function stateBadgeClassName(state: StageState): string {
  const base = "rounded border px-2 py-1 text-[11px] font-bold uppercase";
  if (state === "completed") return `${base} border-good text-good`;
  if (state === "current") return `${base} border-machine text-machine`;
  if (state === "failed") return `${base} border-serious text-serious`;
  return `${base} border-rule text-muted`;
}

function nodeClassName(state: StageState): string {
  const base =
    "flex size-10 shrink-0 items-center justify-center rounded border font-display text-body-sm font-bold";
  if (state === "completed") return `${base} border-good bg-good text-surface`;
  if (state === "current") return `${base} border-machine bg-machine text-surface`;
  if (state === "failed") return `${base} border-serious bg-serious text-surface`;
  return `${base} border-rule bg-surface text-muted`;
}

function shortError(value: string | null | undefined): string {
  if (!value) return "";
  const lines = value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  return lines.at(-1) ?? value.trim();
}
