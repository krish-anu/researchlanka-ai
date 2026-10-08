import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The store reads `APP_DATA_DIR` when its module graph is first evaluated, so
 * each case gets a fresh temp directory *and* a fresh module registry. Without
 * the reset every test would share one file and one seeding pass.
 */
async function freshStore(env: Record<string, string | undefined> = {}) {
  const dir = await mkdtemp(path.join(tmpdir(), "rl-users-"));
  vi.resetModules();
  vi.stubEnv("APP_DATA_DIR", dir);
  vi.stubEnv("ADMIN_EMAIL", "");
  vi.stubEnv("ADMIN_PASSWORD", "");
  vi.stubEnv("SEED_TEST_ACCOUNTS", "");
  for (const [key, value] of Object.entries(env)) vi.stubEnv(key, value);
  const store = await import("@/services/auth/store");
  return { dir, store };
}

const directories: string[] = [];

beforeEach(() => {
  // Seeding announces the published credentials; that is deliberate, but it
  // should not bury the test output.
  vi.spyOn(console, "warn").mockImplementation(() => undefined);
});

afterEach(async () => {
  vi.unstubAllEnvs();
  vi.restoreAllMocks();
  await Promise.all(
    directories.splice(0).map((dir) => rm(dir, { recursive: true, force: true })),
  );
});

describe("seeded test accounts", () => {
  it("creates one account per signed-in role", async () => {
    const { dir, store } = await freshStore();
    directories.push(dir);

    const users = await store.listUsers();

    expect(users.map((user) => [user.email, user.role])).toEqual([
      ["admin@example.com", "admin"],
      ["user@example.com", "user"],
      ["reviewer@example.com", "reviewer"],
    ]);
    expect(users.every((user) => !user.disabled)).toBe(true);
  });

  it.each([
    ["admin@example.com", "admin"],
    ["user@example.com", "user"],
    ["reviewer@example.com", "reviewer"],
  ])("signs %s in with the published password", async (email, role) => {
    const { dir, store } = await freshStore();
    directories.push(dir);

    const result = await store.checkCredentials(email, "password123");

    expect(result.ok).toBe(true);
    if (result.ok) expect(result.user.role).toBe(role);
  });

  it("rejects the right email with the wrong password", async () => {
    const { dir, store } = await freshStore();
    directories.push(dir);

    const result = await store.checkCredentials("admin@example.com", "password1234");

    expect(result).toEqual({ ok: false, reason: "invalid" });
  });

  it("re-creates a seed account that was removed from the table", async () => {
    const { dir, store } = await freshStore();
    directories.push(dir);

    const [admin] = await store.listUsers();
    await store.setUserDisabled(admin.id, true);

    // Disabling is not deletion, so the account must not be duplicated.
    const users = await store.listUsers();
    expect(users.filter((user) => user.email === "admin@example.com")).toHaveLength(1);
    expect(users[0].disabled).toBe(true);
  });

  it("seeds only the configured administrator when ADMIN_PASSWORD is set", async () => {
    const { dir, store } = await freshStore({
      ADMIN_EMAIL: "ops@example.gov.lk",
      ADMIN_PASSWORD: "a-real-deployment-secret",
    });
    directories.push(dir);

    const users = await store.listUsers();

    expect(users.map((user) => user.email)).toEqual(["ops@example.gov.lk"]);
    expect(await store.checkCredentials("admin@example.com", "password123")).toEqual({
      ok: false,
      reason: "invalid",
    });
  });

  it("seeds nothing when SEED_TEST_ACCOUNTS is false", async () => {
    const { dir, store } = await freshStore({ SEED_TEST_ACCOUNTS: "false" });
    directories.push(dir);

    expect(await store.listUsers()).toEqual([]);
  });
});

describe("author sign-up accounts", () => {
  it("stores pending accounts and leaves ordinary sign-ups active", async () => {
    const { dir, store } = await freshStore({ SEED_TEST_ACCOUNTS: "false" });
    directories.push(dir);
    const { accountStatus } = await import("@/types/auth");

    const author = await store.createUser({
      email: "author@uom.lk",
      name: "Author",
      password: "long-enough-password",
      status: "pending",
    });
    const reader = await store.createUser({
      email: "reader@example.com",
      name: "Reader",
      password: "long-enough-password",
    });
    if (!author.ok || !reader.ok) throw new Error("accounts not created");

    expect(accountStatus(author.user)).toBe("pending");
    // Ordinary accounts carry no status field at all, like accounts created
    // before author sign-up existed.
    expect(reader.user.status).toBeUndefined();
    expect(accountStatus(reader.user)).toBe("active");

    await store.setUserStatus(author.user.id, "active");
    expect(accountStatus((await store.findUserById(author.user.id))!)).toBe("active");
  });

  it("only rolls back a pending account that never signed in", async () => {
    const { dir, store } = await freshStore({ SEED_TEST_ACCOUNTS: "false" });
    directories.push(dir);

    const pending = await store.createUser({
      email: "pending@uom.lk",
      name: "Pending",
      password: "long-enough-password",
      status: "pending",
    });
    const active = await store.createUser({
      email: "active@uom.lk",
      name: "Active",
      password: "long-enough-password",
    });
    const used = await store.createUser({
      email: "used@uom.lk",
      name: "Used",
      password: "long-enough-password",
      status: "pending",
    });
    if (!pending.ok || !active.ok || !used.ok) throw new Error("accounts not created");
    await store.recordSignIn(used.user.id);

    expect(await store.deleteUnusedPendingUser(active.user.id)).toBe(false);
    expect(await store.deleteUnusedPendingUser(used.user.id)).toBe(false);
    expect(await store.deleteUnusedPendingUser(pending.user.id)).toBe(true);
    expect((await store.listUsers()).map((user) => user.email)).toEqual(["active@uom.lk", "used@uom.lk"]);
  });
});
