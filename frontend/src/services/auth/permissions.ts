/**
 * What each role may do, in one table.
 *
 * Every gate in the app — nav entries, buttons, route guards, server actions —
 * resolves through `can()` against a capability named here, so the answer to
 * "what changes when I sign in?" is readable in a single file rather than
 * scattered across components. Capabilities are listed rather than derived from
 * `ROLE_RANK` because a few of them are genuinely not cumulative.
 */

import type { Role } from "@/types/auth";

export type Capability =
  /* Open to everyone, listed explicitly so the public surface is documented. */
  | "corpus.read"
  | "corpus.export"
  /* Signed-in only. */
  | "library.save"
  | "record.flag"
  | "account.manage"
  /*
   * Author profiles. Granted to every signed-in role; whether this account
   * actually holds an approved profile, and owns the record it is changing,
   * is checked against the backend on each request.
   */
  | "author.apply"
  | "author.contribute"
  /* Administrators only. */
  | "admin.access"
  | "admin.pipeline.view"
  | "admin.pipeline.run"
  | "admin.flags.triage"
  | "admin.resolution.decide"
  | "admin.ai_review.manage"
  | "admin.users.manage"
  | "admin.authors.manage";

const GRANTS: Record<Capability, Role[]> = {
  "corpus.read": ["guest", "user", "reviewer", "admin"],
  "corpus.export": ["guest", "user", "reviewer", "admin"],

  "library.save": ["user", "reviewer", "admin"],
  "record.flag": ["user", "reviewer", "admin"],
  "account.manage": ["user", "reviewer", "admin"],

  "author.apply": ["user", "reviewer", "admin"],
  "author.contribute": ["user", "reviewer", "admin"],

  "admin.access": ["reviewer", "admin"],
  "admin.pipeline.view": ["admin"],
  "admin.pipeline.run": ["admin"],
  "admin.flags.triage": ["admin"],
  "admin.resolution.decide": ["reviewer", "admin"],
  "admin.ai_review.manage": ["admin"],
  "admin.users.manage": ["admin"],
  "admin.authors.manage": ["admin"],
};

export function can(role: Role, capability: Capability): boolean {
  return GRANTS[capability].includes(role);
}

/** Reader-facing summary of a role, used on the sign-in and account screens. */
export const ROLE_CAPABILITY_SUMMARY: Record<Role, string[]> = {
  guest: [
    "Search and read the full public corpus",
    "Browse researcher, institution and topic profiles",
    "Download CSV and JSONL exports",
  ],
  user: [
    "Everything a visitor can do",
    "Save publications to a personal library",
    "Flag records that look wrong, for administrator review",
    "Apply for a verified author profile",
  ],
  reviewer: [
    "Everything a signed-in user can do",
    "Access the AI review queue",
    "Accept or reject assigned AI relevance records",
  ],
  admin: [
    "Everything a signed-in user can do",
    "Pipeline and data-source console",
    "Entity-resolution queue, AI review, and flag triage",
    "Approve author profiles and author-submitted changes",
    "Grant, revoke and suspend accounts",
  ],
};
