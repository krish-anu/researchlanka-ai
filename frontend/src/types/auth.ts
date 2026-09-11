/**
 * The three roles the web platform recognises.
 *
 * `guest` is not stored anywhere — it is what the app assumes when no valid
 * session cookie is present, so "unsigned visitor" is a first-class role rather
 * than the absence of one. That keeps every permission check a single
 * `can(role, capability)` call instead of a null check followed by a role check.
 */
export type Role = "guest" | "user" | "admin";

export const ROLES: Role[] = ["guest", "user", "admin"];

/** Roles are ordered: a higher rank includes everything below it. */
export const ROLE_RANK: Record<Role, number> = {
  guest: 0,
  user: 1,
  admin: 2,
};

export const ROLE_LABEL: Record<Role, string> = {
  guest: "Visitor",
  user: "Signed in",
  admin: "Administrator",
};

export const ROLE_DESCRIPTION: Record<Role, string> = {
  guest:
    "Anyone on the open web. Reads the public corpus, searches, and exports — no account, nothing saved.",
  user:
    "A signed-in researcher or analyst. Everything a visitor can do, plus a saved library and the ability to flag suspect records.",
  admin:
    "Platform steward. Everything a signed-in user can do, plus the pipeline console, the entity-resolution queue, flag triage, and role management.",
};

export function isRole(value: unknown): value is Role {
  return typeof value === "string" && (ROLES as string[]).includes(value);
}

/** A role that can actually own an account — `guest` cannot be stored. */
export type AccountRole = Exclude<Role, "guest">;

export function isAccountRole(value: unknown): value is AccountRole {
  return value === "user" || value === "admin";
}

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
}

/** What the session cookie carries and what components are allowed to see. */
export interface SessionUser {
  id: string;
  email: string;
  name: string;
  role: AccountRole;
}

/** The resolved viewer, including the unsigned case. */
export type Viewer =
  | { role: "guest"; user: null }
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
