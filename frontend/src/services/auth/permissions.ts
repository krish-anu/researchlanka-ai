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
  /* Administrators only. */
  | "admin.access"
  | "admin.pipeline.view"
  | "admin.flags.triage"
  | "admin.resolution.decide"
  | "admin.users.manage";

const GRANTS: Record<Capability, Role[]> = {
  "corpus.read": ["guest", "user", "admin"],
  "corpus.export": ["guest", "user", "admin"],

  "library.save": ["user", "admin"],
  "record.flag": ["user", "admin"],
  "account.manage": ["user", "admin"],

  "admin.access": ["admin"],
  "admin.pipeline.view": ["admin"],
  "admin.flags.triage": ["admin"],
  "admin.resolution.decide": ["admin"],
  "admin.users.manage": ["admin"],
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
  ],
  admin: [
    "Everything a signed-in user can do",
    "Pipeline and data-source console",
    "Entity-resolution queue and flag triage",
    "Grant, revoke and suspend accounts",
  ],
};
