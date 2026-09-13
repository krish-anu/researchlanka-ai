import { NextResponse } from "next/server";
import { appendFile, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

import { can } from "@/services/auth/permissions";
import { getViewer } from "@/services/auth/server";
import {
  BACKEND_ROOT,
  INCREMENTAL_LOG_DIR,
  readIncrementalRunSnapshot,
  writeIncrementalStatus,
} from "@/services/admin/incremental";

interface RunRequest {
  fromDate?: string;
  toDate?: string;
  reviewThreshold?: string;
}

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

export async function POST(request: Request) {
  const viewer = await getViewer();
  if (!can(viewer.role, "admin.pipeline.view")) {
    return NextResponse.json(
      { error: { code: "forbidden", message: "Administrator access required." } },
      { status: 403 },
    );
  }

  const active = await readIncrementalRunSnapshot();
  if (active.status === "running" || active.status === "queued") {
    return NextResponse.json(
      {
        error: {
          code: "already_running",
          message: "An incremental AI update is already running.",
        },
      },
      { status: 409 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as RunRequest;
  const fromDate = body.fromDate?.trim();
  const toDate = body.toDate?.trim();
  const reviewThreshold = body.reviewThreshold?.trim() || "0.6";

  if (fromDate && !DATE_PATTERN.test(fromDate)) {
    return validationError("fromDate must use YYYY-MM-DD.");
  }
  if (toDate && !DATE_PATTERN.test(toDate)) {
    return validationError("toDate must use YYYY-MM-DD.");
  }

  const threshold = Number(reviewThreshold);
  if (!Number.isFinite(threshold) || threshold < 0 || threshold > 1) {
    return validationError("reviewThreshold must be a number from 0 to 1.");
  }

  await mkdir(INCREMENTAL_LOG_DIR, { recursive: true });
  const runStamp = new Date().toISOString().replace(/[-:]/g, "").replace(/\..+/, "Z");
  const logPath = path.join(INCREMENTAL_LOG_DIR, `${runStamp}.log`);
  const args = incrementalArgs({ fromDate, toDate, reviewThreshold });
  const python = existsSync(path.join(BACKEND_ROOT, ".venv", "bin", "python"))
    ? path.join(BACKEND_ROOT, ".venv", "bin", "python")
    : "python";
  const backendModule = path.join(BACKEND_ROOT, "src", "pipeline", "incremental_update.py");

  if (!existsSync(backendModule)) {
    return NextResponse.json(
      {
        error: {
          code: "backend_job_missing",
          message:
            "backend/src/pipeline/incremental_update.py is missing, so the manual update cannot be started from the UI.",
        },
      },
      { status: 501 },
    );
  }

  const child = spawn(python, args, {
    cwd: BACKEND_ROOT,
    detached: false,
    env: process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });

  let stdout = "";
  let stderr = "";
  const startedAt = nowIso();

  await writeIncrementalStatus({
    status: "running",
    pid: child.pid,
    started_at: startedAt,
    message: "Incremental AI publication update is running.",
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
    const result = extractResult(stdout);
    void writeIncrementalStatus({
      status: code === 0 ? "succeeded" : "failed",
      pid: child.pid,
      started_at: startedAt,
      finished_at: nowIso(),
      message:
        code === 0
          ? "Incremental AI publication update completed."
          : `Incremental AI publication update failed with exit code ${code}.`,
      review_threshold: threshold,
      requested_from_date: fromDate ?? null,
      requested_to_date: toDate ?? null,
      log_path: logPath,
      result,
      error: code === 0 ? undefined : stderr.slice(-4000),
    });
  });

  return NextResponse.json(
    {
      data: {
        status: "running",
        pid: child.pid,
        logPath,
        message: "Incremental AI publication update started.",
      },
    },
    { status: 202 },
  );
}

function validationError(message: string) {
  return NextResponse.json(
    { error: { code: "invalid_request", message } },
    { status: 400 },
  );
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
