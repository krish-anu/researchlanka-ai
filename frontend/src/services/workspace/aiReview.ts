import type { QueryParams } from "@/services/api";
import { backendRequest } from "@/services/backend";
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
    status: view === "completed" ? "completed" : status,
    confidence,
    reviewer,
    q,
  };
  const result = await backendRequest<AIReviewPage>("/admin/ai-review", {
    params,
    actor,
  });
  if (!result.ok) {
    console.warn("[admin] Could not load AI review queue", result.message);
    return EMPTY_PAGE;
  }
  return result.data ?? EMPTY_PAGE;
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
  const result = await backendRequest("/admin/ai-review/decide", {
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
  const result = await backendRequest("/admin/ai-review/retry-sync", {
    method: "POST",
    actor: input.actor,
    body: { publication_key: input.publicationKey },
  });
  return result.ok ? { ok: true } : { ok: false, message: result.message };
}

export async function assignPendingAIReviews(input: {
  actor: SessionUser;
}): Promise<{ ok: true; assigned: number } | { ok: false; message: string }> {
  const result = await backendRequest<{
    assignment?: { assigned?: number };
  }>("/admin/ai-review/backfill", {
    method: "POST",
    actor: input.actor,
  });
  if (!result.ok) return { ok: false, message: result.message };
  return {
    ok: true,
    assigned: Number(result.data?.assignment?.assigned ?? 0),
  };
}
