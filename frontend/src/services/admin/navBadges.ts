import { cache } from "react";

import type { Role } from "@/types/auth";
import { countPendingAIReviewCandidates } from "@/services/workspace/aiReview";
import { countPendingCandidates } from "@/services/workspace/resolution";
import { countOpenFlags } from "@/services/workspace/store";

export interface AdminNavBadges {
  flags: number;
  review: number;
  aiReview: number;
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
  const [flags, review, aiReview] = await Promise.all([
    role === "admin" ? safeCount(countOpenFlags) : Promise.resolve(0),
    role === "admin" ? safeCount(countPendingCandidates) : Promise.resolve(0),
    safeCount(countPendingAIReviewCandidates),
  ]);
  return { flags, review, aiReview };
});
