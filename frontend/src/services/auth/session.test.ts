import { beforeAll, describe, expect, it } from "vitest";

import { createSessionToken, readSessionToken, SESSION_MAX_AGE_SECONDS } from "@/services/auth/session";
import { toBase64Url } from "@/services/auth/base64";
import type { SessionUser } from "@/types/auth";

const SECRET = "a-test-secret-that-is-at-least-32-characters";

beforeAll(() => {
  process.env.AUTH_SECRET = SECRET;
});

const USER: SessionUser = {
  id: "usr_1",
  email: "researcher@uoc.lk",
  name: "R Silva",
  role: "user",
};

const ADMIN: SessionUser = { ...USER, id: "usr_2", role: "admin" };

function forge(payload: Record<string, unknown>, signature = "AAAA"): string {
  const body = toBase64Url(new TextEncoder().encode(JSON.stringify(payload)));
  return `${body}.${signature}`;
}

describe("round trip", () => {
  it("returns the same user it signed", async () => {
    const token = await createSessionToken(USER);

    expect(await readSessionToken(token)).toEqual(USER);
  });

  it("preserves the admin role", async () => {
    const session = await readSessionToken(await createSessionToken(ADMIN));

    expect(session?.role).toBe("admin");
  });
});

/**
 * Everything below is the security boundary: a token that survives any of these
 * would let a visitor choose their own role. `readSessionToken` must return
 * null — never throw, since the caller treats an absent session as `guest` and
 * an exception would surface as a 500 instead of a sign-in prompt.
 */
describe("rejects anything it did not sign", () => {
  it("rejects a payload with a forged signature", async () => {
    const token = forge({ ...ADMIN, iat: 0, exp: 9_999_999_999 });

    expect(await readSessionToken(token)).toBeNull();
  });

  it("rejects a token whose payload was edited after signing", async () => {
    // The exact privilege escalation the signature exists to stop: take a valid
    // `user` token, swap the role to `admin`, keep the original signature.
    const token = await createSessionToken(USER);
    const [, signature] = token.split(".");
    const tampered = forge({ ...USER, role: "admin", iat: 0, exp: 9_999_999_999 }, signature);

    expect(await readSessionToken(tampered)).toBeNull();
  });

  it("rejects a token signed with a different secret", async () => {
    const token = await createSessionToken(USER);
    process.env.AUTH_SECRET = "a-different-secret-of-at-least-32-chars-xx";

    expect(await readSessionToken(token)).toBeNull();

    process.env.AUTH_SECRET = SECRET;
  });

  it.each([
    ["empty string", ""],
    ["undefined", undefined],
    ["null", null],
    ["no separator", "notatoken"],
    ["empty body", ".signature"],
    ["empty signature", "body."],
    ["non-base64 body", "!!!.???"],
    ["three parts", "a.b.c"],
  ])("rejects a malformed token: %s", async (_label, token) => {
    expect(await readSessionToken(token as string | null | undefined)).toBeNull();
  });

  it("rejects a validly signed token that has expired", async () => {
    const token = await createSessionToken(USER, -1);

    expect(await readSessionToken(token)).toBeNull();
  });

  it("rejects a validly signed token carrying an unknown role", async () => {
    // `guest` is never stored in a session — it is what the app assumes when
    // there is no session at all — so a token claiming it is malformed.
    for (const role of ["guest", "superadmin", "", null]) {
      const token = await createSessionToken({ ...USER, role } as never);
      expect(await readSessionToken(token)).toBeNull();
    }
  });

  it("rejects a validly signed token with no expiry", async () => {
    const body = toBase64Url(new TextEncoder().encode(JSON.stringify(USER)));
    // Sign the real body, so only the missing `exp` can cause the rejection.
    const signed = await createSessionToken(USER);
    const [, signature] = signed.split(".");

    expect(await readSessionToken(`${body}.${signature}`)).toBeNull();
  });
});

describe("expiry", () => {
  it("accepts a token inside its window", async () => {
    expect(await readSessionToken(await createSessionToken(USER, 60))).toEqual(USER);
  });

  it("defaults to a one-week window", () => {
    expect(SESSION_MAX_AGE_SECONDS).toBe(60 * 60 * 24 * 7);
  });
});
