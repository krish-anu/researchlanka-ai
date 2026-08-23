/**
 * The user table.
 *
 * Seeded on read, because a platform whose only privileged screen is
 * unreachable until someone is already an administrator has no way in.
 *
 * Which accounts get seeded depends on how the app is configured:
 *
 *   - `ADMIN_EMAIL` + `ADMIN_PASSWORD` set — the deployment path. Exactly that
 *     one administrator is created, on first run only.
 *   - neither set — the development path. Two fixed accounts are kept in
 *     place, one per signed-in role, so both sides of the role system can be
 *     exercised without going through sign-up. Their credentials are published
 *     in the README and are therefore public: set `SEED_TEST_ACCOUNTS=false`
 *     (or configure `ADMIN_PASSWORD`) anywhere that is not a test machine.
 */

import { hashPassword, verifyPassword } from "@/services/auth/password";
import { newId, nowIso, readCollection, updateCollection } from "@/services/store/jsonFile";
import type { AccountRole, UserRecord } from "@/types/auth";

const COLLECTION = "users";
const EMPTY: UserRecord[] = [];

interface SeedAccount {
  email: string;
  password: string;
  name: string;
  role: AccountRole;
}

/** Fixed development logins. Known credentials — never enable in production. */
const TEST_ACCOUNTS: SeedAccount[] = [
  {
    email: "admin@example.com",
    password: "password123",
    name: "Test administrator",
    role: "admin",
  },
  {
    email: "user@example.com",
    password: "password123",
    name: "Test user",
    role: "user",
  },
];

const CONFIGURED_ADMIN_EMAIL = "admin@researchlanka.lk";

function testAccountsEnabled(): boolean {
  // A configured administrator means this is a real deployment, so the known
  // credentials stay out of it whatever `SEED_TEST_ACCOUNTS` says.
  if (process.env.ADMIN_PASSWORD) return false;
  return process.env.SEED_TEST_ACCOUNTS !== "false";
}

export function normaliseEmail(email: string): string {
  return email.trim().toLowerCase();
}

/** Which seed accounts are not in the table yet. */
function missingSeeds(users: UserRecord[]): SeedAccount[] {
  if (process.env.ADMIN_PASSWORD) {
    // Configured administrator: first run only, so an operator who later
    // renames or removes the account does not get it silently recreated.
    if (users.length > 0) return [];
    return [
      {
        email: normaliseEmail(process.env.ADMIN_EMAIL ?? CONFIGURED_ADMIN_EMAIL),
        password: process.env.ADMIN_PASSWORD,
        name: "Platform administrator",
        role: "admin",
      },
    ];
  }

  if (!testAccountsEnabled()) return [];
  const present = new Set(users.map((user) => user.email));
  return TEST_ACCOUNTS.filter((seed) => !present.has(normaliseEmail(seed.email)));
}

/**
 * Create any seed account that is missing.
 *
 * Hashing is the expensive part, so the common case — everything already
 * seeded — costs one file read and no key derivation. The write runs inside
 * the collection lock and re-checks there, so two simultaneous first requests
 * cannot both insert the same account.
 */
async function ensureSeeded(): Promise<void> {
  const existing = await readCollection<UserRecord[]>(COLLECTION, EMPTY);
  const pending = missingSeeds(existing);
  if (pending.length === 0) return;

  // One timestamp for the whole batch: hashing finishes in an unpredictable
  // order, and distinct timestamps would let a fresh install list the seeded
  // accounts in a different order each time.
  const createdAt = nowIso();
  const prepared = await Promise.all(
    pending.map(async (seed) => ({
      seed,
      record: {
        id: newId("usr"),
        email: normaliseEmail(seed.email),
        name: seed.name,
        role: seed.role,
        password: await hashPassword(seed.password),
        created_at: createdAt,
        last_login_at: null,
        disabled: false,
      } satisfies UserRecord,
    })),
  );

  const created = await updateCollection<UserRecord[], SeedAccount[]>(
    COLLECTION,
    EMPTY,
    (users) => {
      const present = new Set(users.map((user) => user.email));
      const fresh = prepared.filter((entry) => !present.has(entry.record.email));
      return {
        next: [...users, ...fresh.map((entry) => entry.record)],
        result: fresh.map((entry) => entry.seed),
      };
    },
  );

  if (created.length === 0 || process.env.ADMIN_PASSWORD) return;

  console.warn("[auth] Seeded development accounts with published credentials:");
  for (const seed of created) {
    console.warn(`[auth]   ${seed.email} / ${seed.password}  (${seed.role})`);
  }
  console.warn(
    "[auth] Set ADMIN_EMAIL and ADMIN_PASSWORD, or SEED_TEST_ACCOUNTS=false, before deploying.",
  );
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
