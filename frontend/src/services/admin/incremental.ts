import { spawn } from "node:child_process";
import { constants } from "node:fs";
import { access, mkdir, open, readFile } from "node:fs/promises";
import path from "node:path";

export type IncrementalJobStatusName =
  | "idle"
  | "running"
  | "succeeded"
  | "failed";

export interface IncrementalJobStatus {
  status: IncrementalJobStatusName;
  pid: number | null;
  started_at: string | null;
  finished_at: string | null;
  message: string;
  model: string | null;
  db_labels: string[];
  log_path: string | null;
  result?: {
    run_id: string;
    from_date: string;
    to_date: string;
    records_collected: number;
    records_selected_for_db: number;
    records_loaded: number;
    csv_output: string;
    db_load_output: string;
    checkpoint_output: string;
  };
}

export interface StartIncrementalJobInput {
  model?: string;
  fromDate?: string;
  toDate?: string;
  confidenceReviewThreshold?: string;
}

const REPO_ROOT = process.env.RESEARCHLANKA_ROOT
  ? path.resolve(process.env.RESEARCHLANKA_ROOT)
  : path.resolve(process.cwd(), "..");
const BACKEND_DIR = path.join(REPO_ROOT, "backend");
const STATUS_PATH =
  process.env.RESEARCHLANKA_INCREMENTAL_STATUS_PATH ??
  path.join(BACKEND_DIR, "outputs", "incremental", "ui_status.json");
const CONFIGURED_PYTHON =
  process.env.RESEARCHLANKA_BACKEND_PYTHON ??
  path.join(BACKEND_DIR, ".venv", "bin", "python");

export async function readIncrementalJobStatus(): Promise<IncrementalJobStatus> {
  try {
    const raw = await readFile(STATUS_PATH, "utf-8");
    return normalizeStatus(JSON.parse(raw));
  } catch {
    return {
      status: "idle",
      pid: null,
      started_at: null,
      finished_at: null,
      message: "No manual update has been started from this console.",
      model: null,
      db_labels: ["AI"],
      log_path: null,
    };
  }
}

export async function startIncrementalJob(
  input: StartIncrementalJobInput,
): Promise<IncrementalJobStatus> {
  const current = await readIncrementalJobStatus();
  if (current.status === "running" && isProcessRunning(current.pid)) {
    throw new Error("An incremental update is already running.");
  }

  const model =
    input.model?.trim() ||
    process.env.RESEARCHLANKA_AI_RELEVANCE_MODEL_PATH ||
    process.env.INCREMENTAL_MODEL ||
    "";

  const python = await resolvePython();
  const logPath = path.join(
    BACKEND_DIR,
    "outputs",
    "incremental",
    "ui_logs",
    `${new Date().toISOString().replace(/[:.]/g, "")}.log`,
  );
  await mkdir(path.dirname(logPath), { recursive: true });
  const logFile = await open(logPath, "a");

  const args = [
    "scripts/admin/run_incremental_update_job.py",
    "--status",
    STATUS_PATH,
    "--log-path",
    logPath,
    "--db-labels",
    "AI",
  ];
  if (model) args.push("--model", model);
  if (input.fromDate?.trim()) args.push("--from-date", input.fromDate.trim());
  if (input.toDate?.trim()) args.push("--to-date", input.toDate.trim());
  if (input.confidenceReviewThreshold?.trim()) {
    args.push(
      "--confidence-review-threshold",
      input.confidenceReviewThreshold.trim(),
    );
  }

  const child = spawn(python, args, {
    cwd: BACKEND_DIR,
    detached: true,
    env: process.env,
    stdio: ["ignore", logFile.fd, logFile.fd],
  });
  child.unref();
  await logFile.close();

  return {
    status: "running",
    pid: child.pid ?? null,
    started_at: new Date().toISOString(),
    finished_at: null,
    message: "Incremental AI publication update started.",
    model: model || null,
    db_labels: ["AI"],
    log_path: logPath,
  };
}

async function resolvePython(): Promise<string> {
  try {
    await access(CONFIGURED_PYTHON, constants.X_OK);
    return CONFIGURED_PYTHON;
  } catch {
    return "python3";
  }
}

function normalizeStatus(value: unknown): IncrementalJobStatus {
  if (!value || typeof value !== "object") {
    throw new Error("Invalid incremental status payload.");
  }
  const record = value as Record<string, unknown>;
  const status = String(record.status ?? "idle") as IncrementalJobStatusName;
  return {
    status: ["idle", "running", "succeeded", "failed"].includes(status)
      ? status
      : "idle",
    pid: typeof record.pid === "number" ? record.pid : null,
    started_at:
      typeof record.started_at === "string" ? record.started_at : null,
    finished_at:
      typeof record.finished_at === "string" ? record.finished_at : null,
    message:
      typeof record.message === "string"
        ? record.message
        : "No status message is available.",
    model: typeof record.model === "string" ? record.model : null,
    db_labels: Array.isArray(record.db_labels)
      ? record.db_labels.map(String)
      : ["AI"],
    log_path: typeof record.log_path === "string" ? record.log_path : null,
    result:
      record.result && typeof record.result === "object"
        ? (record.result as IncrementalJobStatus["result"])
        : undefined,
  };
}

function isProcessRunning(pid: number | null): boolean {
  if (!pid) return false;
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}
