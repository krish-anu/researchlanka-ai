/**
 * Stateless session tokens.
 *
 * A session is an HMAC-SHA256-signed JSON payload in an httpOnly cookie. There
 * is no server-side session table, which keeps the app deployable as a plain
 * Next.js server with no extra infrastructure — the cost is that revoking a
 * session before it expires means rotating `AUTH_SECRET`, and that a role
 * change only takes effect on the user's next sign-in. Both are called out in
 * the admin UI where they matter.
 *
 * Signing and verification use Web Crypto so the same code path serves
 * middleware (Edge runtime) and server components alike.
 */

import { fromBase64Url, toBase64Url } from "@/services/auth/base64";
import { isAccountRole, type SessionUser } from "@/types/auth";

export const SESSION_COOKIE = "rl_session";

/** Sessions last a working week; long enough to be useful, short enough to age out. */
export const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 7;

const DEV_SECRET = "researchlanka-development-secret-do-not-use-in-production";

interface SessionPayload extends SessionUser {
  /** Issued-at and expiry, both epoch seconds. */
  iat: number;
  exp: number;
}

function secret(): string {
  const configured = process.env.AUTH_SECRET;
  if (configured && configured.length >= 32) return configured;

  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "AUTH_SECRET must be set to at least 32 characters in production.",
    );
  }
  return DEV_SECRET;
}

async function signingKey(): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret()),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign", "verify"],
  );
}

export async function createSessionToken(
  user: SessionUser,
  maxAgeSeconds = SESSION_MAX_AGE_SECONDS,
): Promise<string> {
  const now = Math.floor(Date.now() / 1000);
  const payload: SessionPayload = {
    ...user,
    iat: now,
    exp: now + maxAgeSeconds,
  };
  const body = toBase64Url(
    new TextEncoder().encode(JSON.stringify(payload)),
  );
  const signature = await crypto.subtle.sign(
    "HMAC",
    await signingKey(),
    new TextEncoder().encode(body),
  );
  return `${body}.${toBase64Url(new Uint8Array(signature))}`;
}

/** Returns the session user, or `null` for any malformed, forged or expired token. */
export async function readSessionToken(
  token: string | undefined | null,
): Promise<SessionUser | null> {
  if (!token) return null;

  const [body, signature] = token.split(".");
  if (!body || !signature) return null;

  let valid = false;
  try {
    valid = await crypto.subtle.verify(
      "HMAC",
      await signingKey(),
      fromBase64Url(signature) as BufferSource,
      new TextEncoder().encode(body),
    );
  } catch {
    return null;
  }
  if (!valid) return null;

  let payload: SessionPayload;
  try {
    payload = JSON.parse(new TextDecoder().decode(fromBase64Url(body)));
  } catch {
    return null;
  }

  if (typeof payload.exp !== "number" || payload.exp <= Date.now() / 1000) {
    return null;
  }
  if (
    typeof payload.id !== "string" ||
    typeof payload.email !== "string" ||
    !isAccountRole(payload.role)
  ) {
    return null;
  }

  return {
    id: payload.id,
    email: payload.email,
    name: typeof payload.name === "string" ? payload.name : payload.email,
    role: payload.role,
  };
}

/** Cookie attributes shared by the sign-in and sign-out paths. */
export function sessionCookieOptions(maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge,
  };
}
