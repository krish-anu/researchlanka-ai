/**
 * The user table.
 *
 * Seeded on first read with one administrator, because a platform whose only
 * privileged screen is unreachable until someone is already an administrator
 * has no way in. The seed credentials come from `ADMIN_EMAIL` /
 * `ADMIN_PASSWORD` when set; otherwise a development pair is created and its
 * password is printed once to the server log.
 */

import { hashPassword, verifyPassword } from "@/services/auth/password";
import { newId, nowIso, readCollection, updateCollection } from "@/services/store/jsonFile";
import type { AccountRole, UserRecord } from "@/types/auth";

const COLLECTION = "users";
const EMPTY: UserRecord[] = [];

const DEV_ADMIN_EMAIL = "admin@researchlanka.lk";
const DEV_ADMIN_PASSWORD = "researchlanka-admin";

export function normaliseEmail(email: string): string {
  return email.trim().toLowerCase();
}

/**
 * Create the first administrator if the table is empty.
 *
 * Runs inside the collection lock so two simultaneous first requests cannot
 * both seed, and is a no-op on every call after the first.
 */
async function ensureSeeded(): Promise<void> {
  const existing = await readCollection<UserRecord[]>(COLLECTION, EMPTY);
  if (existing.length > 0) return;

  const email = normaliseEmail(process.env.ADMIN_EMAIL ?? DEV_ADMIN_EMAIL);
  const password = process.env.ADMIN_PASSWORD ?? DEV_ADMIN_PASSWORD;
  const passwordHash = await hashPassword(password);

  const created = await updateCollection<UserRecord[], boolean>(
    COLLECTION,
    EMPTY,
    (users) => {
      if (users.length > 0) return { next: users, result: false };
      const admin: UserRecord = {
        id: newId("usr"),
        email,
        name: "Platform administrator",
        role: "admin",
        password: passwordHash,
        created_at: nowIso(),
        last_login_at: null,
        disabled: false,
      };
      return { next: [admin], result: true };
    },
  );

  if (created && !process.env.ADMIN_PASSWORD) {
    console.warn(
      `[auth] Seeded the first administrator: ${email} / ${DEV_ADMIN_PASSWORD}\n` +
        "[auth] Set ADMIN_EMAIL and ADMIN_PASSWORD before deploying, and delete .data/users.json to re-seed.",
    );
  }
}

export async function listUsers(): Promise<UserRecord[]> {
  await ensureSeeded();
  const users = await readCollection<UserRecord[]>(COLLECTION, EMPTY);
  return [...users].sort((a, b) => a.created_at.localeCompare(b.created_at));
}

export async function findUserByEmail(email: string): Promise<UserRecord | null> {
  const target = normaliseEmail(email);
  const users = await listUsers();
  return users.find((user) => user.email === target) ?? null;
}

export async function findUserById(id: string): Promise<UserRecord | null> {
  const users = await listUsers();
  return users.find((user) => user.id === id) ?? null;
}

export type CreateUserResult =
  | { ok: true; user: UserRecord }
  | { ok: false; reason: "email_taken" };

export async function createUser(input: {
  email: string;
  name: string;
  password: string;
  role?: AccountRole;
}): Promise<CreateUserResult> {
  await ensureSeeded();
  const email = normaliseEmail(input.email);
  const passwordHash = await hashPassword(input.password);

  return updateCollection<UserRecord[], CreateUserResult>(
    COLLECTION,
    EMPTY,
    (users) => {
      if (users.some((user) => user.email === email)) {
        return { next: users, result: { ok: false, reason: "email_taken" } };
      }
      const user: UserRecord = {
        id: newId("usr"),
        email,
        name: input.name.trim() || email,
        role: input.role ?? "user",
        password: passwordHash,
        created_at: nowIso(),
        last_login_at: null,
        disabled: false,
      };
      return { next: [...users, user], result: { ok: true, user } };
    },
  );
}

export type CredentialCheck =
  | { ok: true; user: UserRecord }
  | { ok: false; reason: "invalid" | "disabled" };

/**
 * Verify an email/password pair.
 *
 * An unknown email still runs a hash verification against a dummy digest so the
 * response time does not reveal whether the address exists.
 */
export async function checkCredentials(
  email: string,
  password: string,
): Promise<CredentialCheck> {
  const user = await findUserByEmail(email);

  if (!user) {
    await verifyPassword(password, `pbkdf2-sha256$210000$AAAA$AAAA`);
    return { ok: false, reason: "invalid" };
  }
  if (!(await verifyPassword(password, user.password))) {
    return { ok: false, reason: "invalid" };
  }
  if (user.disabled) return { ok: false, reason: "disabled" };

  return { ok: true, user };
}

async function patchUser(
  id: string,
  patch: (user: UserRecord) => UserRecord,
): Promise<UserRecord | null> {
  return updateCollection<UserRecord[], UserRecord | null>(
    COLLECTION,
    EMPTY,
    (users) => {
      const index = users.findIndex((user) => user.id === id);
      if (index === -1) return { next: users, result: null };
      const updated = patch(users[index]);
      const next = [...users];
      next[index] = updated;
      return { next, result: updated };
    },
  );
}

export function recordSignIn(id: string): Promise<UserRecord | null> {
  return patchUser(id, (user) => ({ ...user, last_login_at: nowIso() }));
}

export function setUserRole(
  id: string,
  role: AccountRole,
): Promise<UserRecord | null> {
  return patchUser(id, (user) => ({ ...user, role }));
}

export function setUserDisabled(
  id: string,
  disabled: boolean,
): Promise<UserRecord | null> {
  return patchUser(id, (user) => ({ ...user, disabled }));
}

/** How many enabled administrators remain — the guard against locking everyone out. */
export async function countActiveAdmins(): Promise<number> {
  const users = await listUsers();
  return users.filter((user) => user.role === "admin" && !user.disabled).length;
}
