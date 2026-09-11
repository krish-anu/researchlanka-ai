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
  fromDate?: string;
  toDate?: string;
  confidenceReviewThreshold?: string;
}

const API_BASE_URL =
  process.env.API_BASE_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://127.0.0.1:8080/api/v1";
const REQUEST_TIMEOUT_MS = 20_000;

export async function readIncrementalJobStatus(): Promise<IncrementalJobStatus> {
  try {
    const response = await fetch(`${API_BASE_URL}/admin/incremental/status`, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (!response.ok) return idleStatus();
    return normalizeStatusPayload(await response.json());
  } catch {
    return idleStatus();
  }
}

export async function startIncrementalJob(
  input: StartIncrementalJobInput,
): Promise<IncrementalJobStatus> {
  const response = await fetch(`${API_BASE_URL}/admin/incremental/run`, {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from_date: input.fromDate?.trim() || undefined,
      to_date: input.toDate?.trim() || undefined,
      confidence_review_threshold:
        input.confidenceReviewThreshold?.trim() || undefined,
    }),
    cache: "no-store",
    signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
  });

  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return normalizeStatusPayload(await response.json());
}

function normalizeStatusPayload(payload: unknown): IncrementalJobStatus {
  const record =
    payload && typeof payload === "object"
      ? (payload as Record<string, unknown>)
      : {};
  const data = record.data ?? payload;
  return normalizeStatus(data);
}

function normalizeStatus(value: unknown): IncrementalJobStatus {
  if (!value || typeof value !== "object") return idleStatus();
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

function idleStatus(): IncrementalJobStatus {
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

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as {
      error?: { message?: string };
    };
    return payload.error?.message ?? `Request failed with HTTP ${response.status}.`;
  } catch {
    return `Request failed with HTTP ${response.status}.`;
  }
}
