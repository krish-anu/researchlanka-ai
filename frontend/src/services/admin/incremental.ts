import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { appendFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import type {
  IncrementalRunResult,
  IncrementalRunSnapshot,
  IncrementalRunStatus,
} from "@/components/admin/IncrementalUpdateDiagram";

interface RawIncrementalStatus {
  status?: string;
  pid?: number | null;
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
  error?: string | null;
  log_path?: string | null;
  db_labels?: string[] | null;
  review_threshold?: number | string | null;
  requested_from_date?: string | null;
  requested_to_date?: string | null;
  result?: IncrementalRunResult | null;
}

export type IncrementalJobStatus = IncrementalRunSnapshot;

export interface StartIncrementalJobInput {
  fromDate?: string | null;
  toDate?: string | null;
  reviewThreshold?: string | number | null;
  from_date?: string | null;
  to_date?: string | null;
  review_threshold?: string | number | null;
  confidenceReviewThreshold?: string | number | null;
  confidence_review_threshold?: string | number | null;
}

export type StartIncrementalJobResult =
  | {
      ok: true;
      status: IncrementalJobStatus;
      message: string;
      pid?: number;
      logPath: string;
      db_labels: string[];
    }
  | {
      ok: false;
      status?: IncrementalJobStatus;
      message: string;
      code: string;
    };

const ROOT = process.cwd().endsWith(`${path.sep}frontend`)
  ? path.resolve(process.cwd(), "..")
  : process.cwd();
const STATUS_PATH = path.join(ROOT, "backend", "outputs", "incremental", "ui_status.json");

export const INCREMENTAL_STATUS_PATH = STATUS_PATH;
export const INCREMENTAL_ROOT = path.dirname(STATUS_PATH);
export const INCREMENTAL_LOG_DIR = path.join(INCREMENTAL_ROOT, "ui_logs");
export const BACKEND_ROOT = path.join(ROOT, "backend");

export async function readIncrementalRunSnapshot(): Promise<IncrementalRunSnapshot> {
  try {
    const payload = JSON.parse(
      await readFile(STATUS_PATH, "utf-8"),
    ) as RawIncrementalStatus;
    return await normalizeSnapshot(payload);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== "ENOENT") {
      console.warn("Could not read incremental update status", error);
    }
    return {
      status: "idle",
      message: "No incremental AI update has been started from this console.",
      db_labels: ["AI"],
    };
  }
}

export async function readIncrementalJobStatus(): Promise<IncrementalJobStatus> {
  return readIncrementalRunSnapshot();
}

export async function startIncrementalJob(
  input: StartIncrementalJobInput | FormData = {},
): Promise<StartIncrementalJobResult> {
  const request = normalizeStartInput(input);
  const active = await readIncrementalRunSnapshot();
  if (active.status === "running" || active.status === "queued") {
    return {
      ok: false,
      status: active,
      code: "already_running",
      message: "An incremental AI update is already running.",
    };
  }

  const fromDate = (request.fromDate ?? request.from_date)?.trim() || undefined;
  const toDate = (request.toDate ?? request.to_date)?.trim() || undefined;
  const reviewThreshold =
    String(
      request.reviewThreshold ??
        request.confidenceReviewThreshold ??
        request.review_threshold ??
        request.confidence_review_threshold ??
        "0.6",
    ).trim() || "0.6";
  const threshold = Number(reviewThreshold);

  if (fromDate && !isIsoDate(fromDate)) {
    return { ok: false, code: "invalid_request", message: "fromDate must use YYYY-MM-DD." };
  }
  if (toDate && !isIsoDate(toDate)) {
    return { ok: false, code: "invalid_request", message: "toDate must use YYYY-MM-DD." };
  }
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
    return {
      ok: false,
      code: "invalid_request",
      message: "reviewThreshold must be a number from 0 to 1.",
    };
  }

  const backendModule = path.join(BACKEND_ROOT, "src", "pipeline", "incremental_update.py");
  if (!existsSync(backendModule)) {
    return {
      ok: false,
      code: "backend_job_missing",
      message:
        "backend/src/pipeline/incremental_update.py is missing, so the manual update cannot be started from the UI.",
    };
  }

  await mkdir(INCREMENTAL_LOG_DIR, { recursive: true });
  const runStamp = nowIso().replace(/[-:]/g, "").replace(/\..+/, "");
  const logPath = path.join(INCREMENTAL_LOG_DIR, `${runStamp}.log`);
  const python = existsSync(path.join(BACKEND_ROOT, ".venv", "bin", "python"))
    ? path.join(BACKEND_ROOT, ".venv", "bin", "python")
    : "python";
  const args = incrementalArgs({ fromDate, toDate, reviewThreshold });
  const child = spawn(python, args, {
    cwd: BACKEND_ROOT,
    detached: false,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  const startedAt = nowIso();
  let stdout = "";
  let stderr = "";

  await writeIncrementalStatus({
    status: "running",
    pid: child.pid,
    started_at: startedAt,
    message: "Incremental AI publication update is running.",
    db_labels: ["AI"],
    review_threshold: threshold,
    requested_from_date: fromDate ?? null,
    requested_to_date: toDate ?? null,
    log_path: logPath,
  });

  child.stdout.on("data", (chunk: Buffer) => {
    const text = chunk.toString();
    stdout += text;
    void appendFile(logPath, text);
  });
  child.stderr.on("data", (chunk: Buffer) => {
    const text = chunk.toString();
    stderr += text;
    void appendFile(logPath, text);
  });
  child.on("close", (code) => {
    void writeIncrementalStatus({
      status: code === 0 ? "succeeded" : "failed",
      pid: child.pid,
      started_at: startedAt,
      finished_at: nowIso(),
      message:
        code === 0
          ? "Incremental AI publication update completed."
          : `Incremental AI publication update failed with exit code ${code}.`,
      db_labels: ["AI"],
      review_threshold: threshold,
      requested_from_date: fromDate ?? null,
      requested_to_date: toDate ?? null,
      log_path: logPath,
      result: extractResult(stdout),
      error: code === 0 ? undefined : stderr.slice(-4000),
    });
  });

  return {
    ok: true,
    status: await readIncrementalRunSnapshot(),
    message: "Incremental AI publication update started.",
    pid: child.pid,
    logPath,
    db_labels: ["AI"],
  };
}

async function normalizeSnapshot(
  payload: RawIncrementalStatus,
): Promise<IncrementalRunSnapshot> {
  const result = payload.result ?? {};
  const collected =
    numberOrNull(result.records_collected) ??
    (await countCsvRows(result.csv_output));
  const selected =
    numberOrNull(result.records_selected_for_db) ??
    (await countCsvRows(result.db_load_output));
  const status = normalizeStatus(payload.status);
  const message = payload.message ?? defaultStatusMessage(status);
  const fromDate = result.from_date ?? payload.requested_from_date ?? null;
  const toDate = result.to_date ?? payload.requested_to_date ?? null;
  const startedAt = payload.started_at ?? null;
  const finishedAt = payload.finished_at ?? null;
  const logPath = payload.log_path ?? null;

  return {
    status,
    fromDate,
    toDate,
    reviewThreshold: payload.review_threshold ?? null,
    startedAt,
    finishedAt,
    started_at: startedAt,
    finished_at: finishedAt,
    collected,
    selected,
    loaded: numberOrNull(result.records_loaded),
    message,
    error: payload.error ?? null,
    logPath,
    log_path: logPath,
    result,
    db_labels: payload.db_labels ?? ["AI"],
  };
}

export async function writeIncrementalStatus(
  payload: RawIncrementalStatus,
): Promise<void> {
  await mkdir(INCREMENTAL_ROOT, { recursive: true });
  await writeFile(
    INCREMENTAL_STATUS_PATH,
    `${JSON.stringify(payload, null, 2)}\n`,
    "utf-8",
  );
}

function normalizeStatus(value: string | undefined): IncrementalRunStatus {
  if (
    value === "queued" ||
    value === "running" ||
    value === "succeeded" ||
    value === "failed"
  ) {
    return value;
  }
  return "idle";
}

function defaultStatusMessage(status: IncrementalRunStatus): string {
  if (status === "queued") return "Incremental AI publication update is queued.";
  if (status === "running") return "Incremental AI publication update is running.";
  if (status === "succeeded") return "Incremental AI publication update completed.";
  if (status === "failed") return "Incremental AI publication update failed.";
  return "No incremental AI update has been started from this console.";
}

function numberOrNull(value: number | null | undefined): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

async function countCsvRows(pathValue: string | null | undefined): Promise<number | null> {
  if (!pathValue) return null;
  try {
    const text = await readFile(pathValue, "utf-8");
    const lines = text.split(/\r?\n/).filter((line) => line.trim());
    return Math.max(lines.length - 1, 0);
  } catch {
    return null;
  }
}

function isIsoDate(value: string): boolean {
  return /^\d{4}-\d{2}-\d{2}$/.test(value);
}

function normalizeStartInput(
  input: StartIncrementalJobInput | FormData,
): StartIncrementalJobInput {
  if (isFormData(input)) {
    return {
      fromDate: stringFormValue(input, "fromDate") ?? stringFormValue(input, "from_date"),
      toDate: stringFormValue(input, "toDate") ?? stringFormValue(input, "to_date"),
      reviewThreshold:
        stringFormValue(input, "reviewThreshold") ??
        stringFormValue(input, "confidenceReviewThreshold") ??
        stringFormValue(input, "confidence_review_threshold") ??
        stringFormValue(input, "review_threshold"),
    };
  }
  return input as StartIncrementalJobInput;
}

function stringFormValue(formData: FormData, key: string): string | null {
  const value = formData.get(key);
  return typeof value === "string" ? value : null;
}

function isFormData(value: StartIncrementalJobInput | FormData): value is FormData {
  return typeof FormData !== "undefined" && value instanceof FormData;
}

function incrementalArgs({
  fromDate,
  toDate,
  reviewThreshold,
}: {
  fromDate?: string;
  toDate?: string;
  reviewThreshold: string;
}) {
  const args = [
    "-m",
    "src.pipeline.incremental_update",
    "--state",
    "outputs/incremental/state.json",
    "--state-backend",
    process.env.RESEARCHLANKA_INCREMENTAL_STATE_BACKEND ?? "database",
    "--state-key",
    process.env.RESEARCHLANKA_INCREMENTAL_STATE_KEY ?? "incremental_update",
    "--output-root",
    "outputs/incremental/runs",
    "--confidence-review-threshold",
    reviewThreshold,
  ];
  if (fromDate) args.push("--from-date", fromDate);
  if (toDate) args.push("--end-date", toDate);
  return args;
}

function extractResult(stdout: string) {
  const starts = [...stdout.matchAll(/\{/g)].map((match) => match.index ?? -1);
  for (const start of starts.reverse()) {
    try {
      return JSON.parse(stdout.slice(start));
    } catch {
      continue;
    }
  }
  return null;
}

function nowIso(): string {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}
