/**
 * The roles the web platform recognises.
 *
 * `guest` is not stored anywhere — it is what the app assumes when no valid
 * session cookie is present, so "unsigned visitor" is a first-class role rather
 * than the absence of one. That keeps every permission check a single
 * `can(role, capability)` call instead of a null check followed by a role check.
 */
export type Role = "guest" | "user" | "reviewer" | "admin";

export const ROLES: Role[] = ["guest", "user", "reviewer", "admin"];

/** Roles are ordered: a higher rank includes everything below it. */
export const ROLE_RANK: Record<Role, number> = {
  guest: 0,
  user: 1,
  reviewer: 2,
  admin: 3,
};

export const ROLE_LABEL: Record<Role, string> = {
  guest: "Visitor",
  user: "Signed in",
  reviewer: "Reviewer",
  admin: "Administrator",
};

export const ROLE_DESCRIPTION: Record<Role, string> = {
  guest:
    "Anyone on the open web. Reads the public corpus, searches, and exports — no account, nothing saved.",
  user:
    "A signed-in researcher or analyst. Everything a visitor can do, plus a saved library and the ability to flag suspect records.",
  reviewer:
    "AI review specialist. Can access the AI review queue and decide assigned AI relevance records, but cannot manage the pipeline, users, flags, or other admin tools.",
  admin:
    "Platform steward. Everything a signed-in user can do, plus the pipeline console, the entity-resolution queue, flag triage, and role management.",
};

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as string[]).includes(value);
}

/** A role that can actually own an account — `guest` cannot be stored. */
export type AccountRole = Exclude<Role, "guest">;

export function isAccountRole(value: unknown): value is AccountRole {
  return value === "user" || value === "reviewer" || value === "admin";
}

/**
 * Whether an account may use what its role grants.
 *
 * Only author sign-ups start `pending`: they wait for an administrator to
 * approve the author application before the account works. Ordinary sign-ups
 * are `active` immediately. `rejected` keeps the account able to sign in and
 * read the decision, nothing more. This is separate from `disabled`, which is
 * a suspension of an account that was already in use.
 */
export type AccountStatus = "active" | "pending" | "rejected";

/** Full stored record. The password hash never leaves the server. */
export interface UserRecord {
  id: string;
  email: string;
  name: string;
  role: AccountRole;
  /** Encoded PBKDF2 digest — see `services/auth/password.ts`. */
  password: string;
  created_at: string;
  last_login_at: string | null;
  disabled: boolean;
  /** Absent on accounts created before author sign-up existed; read as active. */
  status?: AccountStatus;
}

export function accountStatus(record: Pick<UserRecord, "status">): AccountStatus {
  return record.status ?? "active";
}

/** What the session cookie carries and what components are allowed to see. */
export interface SessionUser {
  id: string;
  email: string;
  name: string;
  role: AccountRole;
}

/**
 * The resolved viewer, including the unsigned case.
 *
 * A signed-in account that is not yet active (an author application waiting
 * for approval, or a rejected one) resolves as a guest — every capability
 * check treats it as unsigned — with `applicant` set, so the few screens that
 * serve applicants can still say who they are.
 */
export type Viewer =
  | { role: "guest"; user: null; applicant?: SessionUser & { status: AccountStatus } }
  | { role: AccountRole; user: SessionUser };

export const GUEST: Viewer = { role: "guest", user: null };

export function publicUser(record: UserRecord): SessionUser {
  return {
    id: record.id,
    email: record.email,
    name: record.name,
    role: record.role,
  };
}
