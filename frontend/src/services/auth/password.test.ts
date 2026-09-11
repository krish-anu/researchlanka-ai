import { describe, expect, it } from "vitest";

import {
  checkPasswordStrength,
  hashPassword,
  verifyPassword,
} from "@/services/auth/password";

describe("hashPassword", () => {
  it("never stores the password itself", async () => {
    const encoded = await hashPassword("correct horse battery staple");

    expect(encoded).not.toContain("correct horse battery staple");
  });

  it("records the algorithm and cost so a stored hash stays self-describing", async () => {
    // Without these, raising the iteration count later would invalidate every
    // existing hash rather than allowing a gradual re-hash on next sign-in.
    const [algorithm, iterations] = (await hashPassword("a-long-enough-password")).split("$");

    expect(algorithm).toBe("pbkdf2-sha256");
    expect(Number(iterations)).toBeGreaterThanOrEqual(210_000);
  });

  it("salts, so the same password hashes differently every time", async () => {
    const first = await hashPassword("a-long-enough-password");
    const second = await hashPassword("a-long-enough-password");

    expect(first).not.toBe(second);
    // Both must still verify — the salt is stored alongside the digest.
    expect(await verifyPassword("a-long-enough-password", first)).toBe(true);
    expect(await verifyPassword("a-long-enough-password", second)).toBe(true);
  });
});

describe("verifyPassword", () => {
  it("accepts the right password", async () => {
    const encoded = await hashPassword("a-long-enough-password");

    expect(await verifyPassword("a-long-enough-password", encoded)).toBe(true);
  });

  it.each([
    ["a wrong password", "a-different-password"],
    ["a near miss", "a-long-enough-passwore"],
    ["a prefix", "a-long-enough-passwor"],
    ["a different case", "A-Long-Enough-Password"],
    ["an empty string", ""],
  ])("rejects %s", async (_label, attempt) => {
    const encoded = await hashPassword("a-long-enough-password");

    expect(await verifyPassword(attempt, encoded)).toBe(false);
  });

  it.each([
    ["empty", ""],
    ["not encoded at all", "plaintext"],
    ["too few fields", "pbkdf2-sha256$210000$salt"],
    ["unknown algorithm", "md5$1$salt$hash"],
    ["non-numeric cost", "pbkdf2-sha256$many$salt$hash"],
    ["zero cost", "pbkdf2-sha256$0$salt$hash"],
    ["non-base64 payload", "pbkdf2-sha256$210000$!!!$???"],
  ])("returns false rather than throwing on a corrupt stored hash: %s", async (_l, stored) => {
    // A corrupt row must fail the sign-in, not crash the request — otherwise a
    // single bad record takes the whole auth path down.
    await expect(verifyPassword("any-password", stored)).resolves.toBe(false);
  });
});

describe("checkPasswordStrength", () => {
  it("accepts a passphrase at the floor", () => {
    expect(checkPasswordStrength("0123456789")).toBeNull();
    expect(checkPasswordStrength("correct horse battery staple")).toBeNull();
  });

  it("rejects anything shorter than ten characters", () => {
    expect(checkPasswordStrength("123456789")).not.toBeNull();
    expect(checkPasswordStrength("")).not.toBeNull();
  });

  it("rejects an absurdly long password", () => {
    // Not a security rule but a cost one: PBKDF2 over a megabyte of input is a
    // free denial of service.
    expect(checkPasswordStrength("a".repeat(201))).not.toBeNull();
  });

  it("imposes no composition rules, which push people to weaker passwords", () => {
    expect(checkPasswordStrength("aaaaaaaaaaaaaaaaaaaa")).toBeNull();
  });
});
