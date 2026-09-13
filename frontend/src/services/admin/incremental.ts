import { readFile } from "node:fs/promises";
import path from "node:path";

import type {
  IncrementalRunSnapshot,
  IncrementalRunStatus,
} from "@/components/admin/IncrementalUpdateDiagram";

interface RawIncrementalStatus {
  status?: string;
  started_at?: string | null;
  finished_at?: string | null;
  message?: string | null;
  log_path?: string | null;
  result?: {
    from_date?: string | null;
    to_date?: string | null;
    records_collected?: number | null;
    records_selected_for_db?: number | null;
    records_loaded?: number | null;
  } | null;
}

const STATUS_PATH = path.resolve(
  process.cwd(),
  "..",
  "backend",
  "outputs",
  "incremental",
  "ui_status.json",
);

export async function readIncrementalRunSnapshot(): Promise<IncrementalRunSnapshot> {
  try {
    const payload = JSON.parse(
      await readFile(STATUS_PATH, "utf-8"),
    ) as RawIncrementalStatus;
    return normalizeSnapshot(payload);
  } catch (error) {
    const code = (error as NodeJS.ErrnoException).code;
    if (code !== "ENOENT") {
      console.warn("Could not read incremental update status", error);
    }
    return { status: "idle" };
  }
}

function normalizeSnapshot(payload: RawIncrementalStatus): IncrementalRunSnapshot {
  const result = payload.result ?? {};

  return {
    status: normalizeStatus(payload.status),
    fromDate: result.from_date ?? null,
    toDate: result.to_date ?? null,
    startedAt: payload.started_at ?? null,
    finishedAt: payload.finished_at ?? null,
    collected: numberOrNull(result.records_collected),
    selected: numberOrNull(result.records_selected_for_db),
    loaded: numberOrNull(result.records_loaded),
    logPath: payload.log_path ?? null,
  };
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
