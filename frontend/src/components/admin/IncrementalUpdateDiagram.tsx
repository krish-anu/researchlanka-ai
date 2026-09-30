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

  const completed = stages.filter(
    (stage) => stage.state === "completed",
  ).length;

  const failed = stages.some((stage) => stage.state === "failed");

  const progress = failed
    ? Math.round((completed / stages.length) * 100)
    : Math.round((completed / stages.length) * 100);

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
            className={`h-full ${failed ? "bg-serious" : "bg-primary"
              }`}
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
          <li
            key={stage.id}
            className="flex min-w-0 flex-1 flex-col lg:flex-row lg:items-center"
          >
            <div
              title={stage.detail}
              className={`flex min-h-[7rem] w-full flex-col gap-1 rounded-lg border px-3 py-3 ${stageClassName(
                stage.state,
              )}`}
            >
              <div className="flex items-start justify-between gap-2">
                <span className="label-caps text-muted">
                  Step {index + 1}
                </span>

                <span
                  className={stateBadgeClassName(stage.state)}
                >
                  {FLOW_LABELS[stage.state]}
                </span>
              </div>

              <h4 className="mt-2 font-display text-body-sm font-semibold text-ink">
                {stage.label}
              </h4>

              <p className="mt-1 text-xs leading-5 text-ink-secondary">
                {stage.detail}
              </p>

              {stage.output ? (
                <p className="mt-2 rounded border border-rule bg-surface px-2 py-1 text-xs text-muted">
                  {stage.output}
                </p>
              ) : null}

              {stage.metric ? (
                <p className="mt-auto pt-2 data-mono text-primary">
                  {stage.metric}
                </p>
              ) : null}
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

        <Metric
          label="New records"
          value={
            run.newRecords ?? run.result?.records_new_for_db
          }
        />

        <Metric
          label="Updated records"
          value={
            run.updatedRecords ??
            run.result?.records_updated_for_db
          }
        />

        <Metric label="Loaded / updated" value={run.loaded} />
      </dl>
    </div>
  );
}

function buildStages(run: IncrementalRunSnapshot): Stage[] {
  const status = String(run.status || "idle").toLowerCase();

  const failed = status === "failed";
  const done = status === "succeeded";
  const running = status === "running" || status === "queued";

  const collected =
    run.collected ?? run.result?.records_collected;

  const selected =
    run.selected ?? run.result?.records_selected_for_db;

  const loaded =
    run.loaded ?? run.result?.records_loaded;

  const newRecords =
    run.newRecords ?? run.result?.records_new_for_db;

  const updatedRecords =
    run.updatedRecords ?? run.result?.records_updated_for_db;

  const logPath = run.logPath ?? run.log_path;

  const csvOutput = run.result?.csv_output;

  const dbLoadOutput = run.result?.db_load_output;

  const collectedDone = typeof collected === "number";

  const selectedDone = typeof selected === "number";

  const loadedDone = typeof loaded === "number";

  const classifiedDone =
    selectedDone || loadedDone || done;

  const enrichedDone =
    collectedDone || classifiedDone || done;

  const selectedDoneOrFinished =
    selectedDone || loadedDone || done;

  return [
    {
      id: "window",
      label: "Prepare window",
      detail: dateWindow(
        run.fromDate ?? run.result?.from_date,
        run.toDate ?? run.result?.to_date,
      ),
      state:
        failed || done || running
          ? "completed"
          : "remaining",
    },

    {
      id: "fetch",
      label: "Fetch records",
      detail:
        "Collect Sri Lanka publication records for the selected date window.",
      metric: metric(
        collected,
        "records collected",
      ),
      state: stageState({
        failed,
        done: collectedDone || done,
        running,
      }),
    },

    {
      id: "normalize",
      label: "Normalize and match",
      detail:
        "Clean DOI, OpenAlex ID and source IDs, then match incoming records to existing publications.",
      output: csvOutput
        ? `Collected CSV: ${csvOutput}`
        : undefined,
      state: stageState({
        failed,
        done: collectedDone || done,
        running: collectedDone && running,
      }),
    },

    {
      id: "enrich",
      label: "Fetch abstracts/keywords",
      detail:
        "Before preprocessing, fill missing abstracts and keywords from fetched metadata when available.",
      state: stageState({
        failed,
        done: enrichedDone,
        running: collectedDone && running,
      }),
    },

    {
      id: "classify",
      label: "Classify AI relevance",
      detail:
        "Score title, abstract, keywords, topics and concepts with the configured AI relevance model.",
      metric: metric(
        selected,
        "records selected",
      ),
      state: stageState({
        failed,
        done: classifiedDone,
        running: enrichedDone && running,
      }),
    },

    {
      id: "prepare",
      label: "Prepare DB rows",
      detail:
        "Keep the configured DB labels and create the exact load file for PostgreSQL.",
      metric: metric(
        selected,
        "records selected",
      ),
      output: dbLoadOutput
        ? `DB load CSV: ${dbLoadOutput}`
        : undefined,
      state: stageState({
        failed,
        done: selectedDoneOrFinished,
        running: selectedDone && running,
      }),
    },

    {
      id: "load",
      label: "Load database",
      detail:
        "Insert new rows and update matching existing rows by DOI, OpenAlex ID or source ID.",
      metric: loadMetric({
        loaded,
        newRecords,
        updatedRecords,
      }),
      state: stageState({
        failed,
        done: loadedDone || done,
        running:
          selectedDoneOrFinished && running,
      }),
    },

    {
      id: "checkpoint",
      label: "Save checkpoint",
      detail: logPath
        ? `Run log: ${logPath}`
        : "Write checkpoint, message and final status for the admin console.",
      state: failed
        ? "failed"
        : done
          ? "completed"
          : "remaining",
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
  if (failed) return "failed";
  if (done) return "completed";
  if (running) return "current";
  return "remaining";
}

function dateWindow(
  fromDate?: string | null,
  toDate?: string | null,
): string {
  if (fromDate && toDate) {
    return `${fromDate} → ${toDate}`;
  }

  if (fromDate) {
    return `From ${fromDate}`;
  }

  if (toDate) {
    return `Until ${toDate}`;
  }

  return "Resolve the manual or monthly date range.";
}

function metric(
  value: number | null | undefined,
  label: string,
): string | undefined {
  if (typeof value !== "number") {
    return undefined;
  }

  return `${formatNumber(value)} ${label}`;
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
      <svg
        viewBox="0 0 24 24"
        className="size-4 rotate-90 lg:rotate-0"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      >
        <path d="M4 12h14" />
        <path d="M14 6l6 6-6 6" />
      </svg>
    </span>
  );
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
  if (
    typeof newRecords === "number" ||
    typeof updatedRecords === "number"
  ) {
    return `${formatNumber(newRecords ?? 0)} new / ${formatNumber(
      updatedRecords ?? 0,
    )} updated`;
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
    <span
      className={`label-caps rounded border px-3 py-1 ${className}`}
    >
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
        {typeof value === "number"
          ? formatNumber(value)
          : "—"}
      </dd>
    </div>
  );
}

function stageClassName(state: StageState): string {
  if (state === "current") {
    return "relative z-10 -translate-y-1 border-primary bg-surface shadow-md";
  }

  if (state === "completed") {
    return "border-rule bg-surface";
  }

  if (state === "failed") {
    return "border-serious bg-surface";
  }

  return "border-rule bg-wash";
}

function stateBadgeClassName(state: StageState): string {
  const base =
    "rounded border px-2 py-1 text-label font-bold uppercase";

  if (state === "completed") {
    return `${base} border-good text-good`;
  }

  if (state === "current") {
    return `${base} border-machine text-machine`;
  }

  if (state === "failed") {
    return `${base} border-serious text-serious`;
  }

  return `${base} border-rule text-muted`;
}

function shortError(
  value: string | null | undefined,
): string {
  if (!value) return "";

  const lines = value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  return lines.at(-1) ?? value.trim();
}