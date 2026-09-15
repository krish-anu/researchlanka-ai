import { buildQuery, type QueryParams } from "@/services/api";
import type { Pagination } from "@/types/api";
import type { SessionUser } from "@/types/auth";
import type { AIReviewCandidate } from "@/services/workspace/types";

export interface AIReviewStats {
  by_status: Record<string, number>;
  sync_failures: number;
  reviewers: {
    email: string | null;
    name: string | null;
    pending: number;
    completed: number;
    total: number;
  }[];
}

export interface AIReviewPage {
  data: AIReviewCandidate[];
  pagination: Pagination;
  stats: AIReviewStats;
}

const EMPTY_PAGE: AIReviewPage = {
  data: [],
  pagination: { page: 1, page_size: 25, total: 0, total_pages: 1 },
  stats: { by_status: {}, sync_failures: 0, reviewers: [] },
};

const REMOTE_API_BASE_URL =
  process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
const REMOTE_ADMIN_API_TOKEN = process.env.RESEARCHLANKA_ADMIN_API_TOKEN;

export async function listAIReviewCandidates({
  page = 1,
  pageSize = 25,
  view = "mine",
  status,
  confidence,
  reviewer,
  q,
  actor,
}: {
  page?: number;
  pageSize?: number;
  view?: "mine" | "all" | "completed";
  status?: string;
  confidence?: string;
  reviewer?: string;
  q?: string;
  actor?: SessionUser | null;
} = {}): Promise<AIReviewPage> {
  const params: QueryParams = {
    page,
    page_size: pageSize,
    view: view === "all" ? "all" : "mine",
    status: view === "completed" ? undefined : status,
    confidence,
    reviewer,
    q,
  };
  const result = await adminRequest<AIReviewPage>("/admin/ai-review", {
    params,
    actor,
  });
  if (!result.ok) {
    console.warn("[admin] Could not load AI review queue", result.message);
    return EMPTY_PAGE;
  }
  const pageData = result.data ?? EMPTY_PAGE;
  if (view !== "completed") return pageData;
  return {
    ...pageData,
    data: pageData.data.filter((item) => item.review_status !== "pending_review"),
  };
}

export async function countPendingAIReviewCandidates(): Promise<number> {
  const result = await listAIReviewCandidates({
    page: 1,
    pageSize: 1,
    view: "all",
    status: "pending_review",
  });
  return result.stats.by_status.pending_review ?? result.pagination.total;
}

export async function decideAIReview(input: {
  publicationKey: string;
  recordVersion: number;
  decision: "human_accepted" | "human_rejected";
  note: string;
  actor: SessionUser;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  const result = await adminRequest("/admin/ai-review/decide", {
    method: "POST",
    actor: input.actor,
    body: {
      publication_key: input.publicationKey,
      record_version: input.recordVersion,
      decision: input.decision,
      notes: input.note,
    },
  });
  return result.ok ? { ok: true } : { ok: false, message: result.message };
}

export async function retryAIReviewSync(input: {
  publicationKey: string;
  actor: SessionUser;
}): Promise<{ ok: true } | { ok: false; message: string }> {
  const result = await adminRequest("/admin/ai-review/retry-sync", {
    method: "POST",
    actor: input.actor,
    body: { publication_key: input.publicationKey },
  });
  return result.ok ? { ok: true } : { ok: false, message: result.message };
}

type AdminResult<T> =
  | { ok: true; data: T }
  | { ok: false; message: string; code: string };

async function adminRequest<T = unknown>(
  path: string,
  options: {
    method?: "GET" | "POST";
    params?: QueryParams;
    body?: Record<string, unknown>;
    actor?: SessionUser | null;
  } = {},
): Promise<AdminResult<T>> {
  const url = adminApiUrl(path, options.params);
  if (!url) {
    return {
      ok: false,
      code: "api_not_configured",
      message: "API_BASE_URL is not configured for backend admin review endpoints.",
    };
  }
  try {
    const response = await fetch(url, {
      method: options.method ?? "GET",
      headers: adminHeaders(options.actor, options.body ? { "Content-Type": "application/json" } : {}),
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: "no-store",
    });
    const payload = (await response.json().catch(() => ({}))) as {
      data?: T;
      error?: { code?: string; message?: string };
    };
    if (!response.ok) {
      return {
        ok: false,
        code: payload.error?.code ?? `http_${response.status}`,
        message: payload.error?.message ?? `Backend API returned HTTP ${response.status}.`,
      };
    }
    return { ok: true, data: payload.data as T };
  } catch {
    return {
      ok: false,
      code: "api_unreachable",
      message: `Could not reach the backend API at ${REMOTE_API_BASE_URL}.`,
    };
  }
}

function adminApiUrl(path: string, params: QueryParams = {}): string | null {
  if (!REMOTE_API_BASE_URL) return null;
  return `${REMOTE_API_BASE_URL.replace(/\/$/, "")}${path}${buildQuery(params)}`;
}

function adminHeaders(
  actor: SessionUser | null | undefined,
  extra: Record<string, string> = {},
): Record<string, string> {
  return {
    Accept: "application/json",
    ...(REMOTE_ADMIN_API_TOKEN
      ? { "X-ResearchLanka-Admin-Token": REMOTE_ADMIN_API_TOKEN }
      : {}),
    ...(actor
      ? {
          "X-ResearchLanka-Actor-Id": actor.id,
          "X-ResearchLanka-Actor-Email": actor.email,
          "X-ResearchLanka-Actor-Name": actor.name,
        }
      : {}),
    ...extra,
  };
}
