import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import type {
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
  review_threshold?: number | string | null;
  requested_from_date?: string | null;
  requested_to_date?: string | null;
  result?: {
    from_date?: string | null;
    to_date?: string | null;
    csv_output?: string | null;
    db_load_output?: string | null;
    records_collected?: number | null;
    records_selected_for_db?: number | null;
    records_loaded?: number | null;
  } | null;
}

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
    return { status: "idle" };
  }
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

  return {
    status: normalizeStatus(payload.status),
    fromDate: result.from_date ?? payload.requested_from_date ?? null,
    toDate: result.to_date ?? payload.requested_to_date ?? null,
    reviewThreshold: payload.review_threshold ?? null,
    startedAt: payload.started_at ?? null,
    finishedAt: payload.finished_at ?? null,
    collected,
    selected,
    loaded: numberOrNull(result.records_loaded),
    message: payload.message ?? null,
    error: payload.error ?? null,
    logPath: payload.log_path ?? null,
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
