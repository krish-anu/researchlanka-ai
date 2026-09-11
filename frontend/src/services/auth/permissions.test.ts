import { describe, expect, it } from "vitest";

import { can, ROLE_CAPABILITY_SUMMARY, type Capability } from "@/services/auth/permissions";
import { ROLES, ROLE_RANK, isAccountRole, isRole, type Role } from "@/types/auth";

const GUEST_ONLY_CAPABILITIES: Capability[] = ["corpus.read", "corpus.export"];

const SIGNED_IN_CAPABILITIES: Capability[] = [
  "library.save",
  "record.flag",
  "account.manage",
];

const ADMIN_CAPABILITIES: Capability[] = [
  "admin.access",
  "admin.pipeline.view",
  "admin.flags.triage",
  "admin.resolution.decide",
  "admin.users.manage",
];

const ALL: Capability[] = [
  ...GUEST_ONLY_CAPABILITIES,
  ...SIGNED_IN_CAPABILITIES,
  ...ADMIN_CAPABILITIES,
];

/**
 * The grant table is the whole role system: nav visibility, route guards and
 * every server action resolve through `can()`. A wrong entry here is a
 * privilege bug everywhere at once, so each role's full surface is pinned
 * rather than spot-checked.
 */
describe("guest", () => {
  it.each(GUEST_ONLY_CAPABILITIES)("can %s — the corpus stays open", (capability) => {
    expect(can("guest", capability)).toBe(true);
  });

  it.each([...SIGNED_IN_CAPABILITIES, ...ADMIN_CAPABILITIES])(
    "cannot %s",
    (capability) => {
      expect(can("guest", capability)).toBe(false);
    },
  );
});

describe("signed-in user", () => {
  it.each([...GUEST_ONLY_CAPABILITIES, ...SIGNED_IN_CAPABILITIES])(
    "can %s",
    (capability) => {
      expect(can("user", capability)).toBe(true);
    },
  );

  it.each(ADMIN_CAPABILITIES)("cannot %s", (capability) => {
    expect(can("user", capability)).toBe(false);
  });
});

describe("admin", () => {
  it.each(ALL)("can %s", (capability) => {
    expect(can("admin", capability)).toBe(true);
  });
});

describe("the grant table stays coherent", () => {
  it("gives every role strictly more than the one below it", () => {
    // Not enforced by the table's shape — it lists grants explicitly — so it is
    // worth asserting, since an accidental omission would silently take a
    // capability away from admins.
    const held = (role: Role) => ALL.filter((capability) => can(role, capability));

    const guest = held("guest");
    const user = held("user");
    const admin = held("admin");

    expect(guest.every((capability) => user.includes(capability))).toBe(true);
    expect(user.every((capability) => admin.includes(capability))).toBe(true);
    expect(user.length).toBeGreaterThan(guest.length);
    expect(admin.length).toBeGreaterThan(user.length);
  });

  it("grants every admin capability to admins alone", () => {
    for (const capability of ADMIN_CAPABILITIES) {
      expect(can("guest", capability)).toBe(false);
      expect(can("user", capability)).toBe(false);
      expect(can("admin", capability)).toBe(true);
    }
  });

  it("describes every role in the reader-facing summary", () => {
    for (const role of ROLES) {
      expect(ROLE_CAPABILITY_SUMMARY[role].length).toBeGreaterThan(0);
    }
  });
});

describe("role predicates", () => {
  it("recognises the three real roles", () => {
    expect(ROLES).toEqual(["guest", "user", "admin"]);
    for (const role of ROLES) expect(isRole(role)).toBe(true);
  });

  it.each([["superadmin"], [""], [null], [undefined], [42], [{}]])(
    "rejects %s as a role",
    (value) => {
      expect(isRole(value)).toBe(false);
    },
  );

  it("treats guest as a role but not as an account role", () => {
    // A guest has no account by definition — that is what distinguishes them —
    // so a stored user must never carry the role.
    expect(isRole("guest")).toBe(true);
    expect(isAccountRole("guest")).toBe(false);
    expect(isAccountRole("user")).toBe(true);
    expect(isAccountRole("admin")).toBe(true);
  });

  it("orders the roles", () => {
    expect(ROLE_RANK.guest).toBeLessThan(ROLE_RANK.user);
    expect(ROLE_RANK.user).toBeLessThan(ROLE_RANK.admin);
  });
});
