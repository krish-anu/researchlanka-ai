import { cache } from "react";

import type { Role } from "@/types/auth";
import { getAuthorQueueSummary } from "@/services/authors";
import { countPendingAIReviewCandidates } from "@/services/workspace/aiReview";
import { countPendingCandidates } from "@/services/workspace/resolution";
import { countOpenFlags } from "@/services/workspace/store";

export interface AdminNavBadges {
  flags: number;
  review: number;
  aiReview: number;
  /** Author applications plus extra claims from approved authors. */
  authors: number;
  contributions: number;
}

async function safeCount(read: () => Promise<number>): Promise<number> {
  try {
    return await read();
  } catch {
    return 0;
  }
}

/** Pending queue sizes for the admin rail and the small-screen section bar. */
export const loadAdminNavBadges = cache(async (role: Role): Promise<AdminNavBadges | undefined> => {
  if (role !== "admin" && role !== "reviewer") return undefined;
  const [flags, review, aiReview, authorQueues] = await Promise.all([
    role === "admin" ? safeCount(countOpenFlags) : Promise.resolve(0),
    role === "admin" ? safeCount(countPendingCandidates) : Promise.resolve(0),
    safeCount(countPendingAIReviewCandidates),
    role === "admin" ? getAuthorQueueSummary() : Promise.resolve(null),
  ]);
  const queues = authorQueues?.ok ? authorQueues.data : null;
  return {
    flags,
    review,
    aiReview,
    authors: queues ? queues.applications + queues.claims : 0,
    contributions: queues?.contributions ?? 0,
  };
});
