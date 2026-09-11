/**
 * Password hashing.
 *
 * PBKDF2-SHA256 via Web Crypto rather than node:crypto's scrypt, because the
 * same module is imported from route handlers, server actions and (indirectly)
 * middleware — Web Crypto is the one API present in every one of those
 * runtimes. Iteration count follows the OWASP 2023 floor for PBKDF2-SHA256.
 */

import { fromBase64, toBase64 } from "@/services/auth/base64";

const ALGORITHM = "pbkdf2-sha256";
const ITERATIONS = 210_000;
const SALT_BYTES = 16;
const KEY_BITS = 256;

async function derive(
  password: string,
  salt: Uint8Array,
  iterations: number,
): Promise<Uint8Array> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(password),
    "PBKDF2",
    false,
    ["deriveBits"],
  );
  const bits = await crypto.subtle.deriveBits(
    { name: "PBKDF2", hash: "SHA-256", salt: salt as BufferSource, iterations },
    key,
    KEY_BITS,
  );
  return new Uint8Array(bits);
}

/** Encoded as `pbkdf2-sha256$iterations$salt$hash`, all base64. */
export async function hashPassword(password: string): Promise<string> {
  const salt = crypto.getRandomValues(new Uint8Array(SALT_BYTES));
  const hash = await derive(password, salt, ITERATIONS);
  return `${ALGORITHM}$${ITERATIONS}$${toBase64(salt)}$${toBase64(hash)}`;
}

/** Length-independent, constant-time comparison. */
function timingSafeEqual(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a[i] ^ b[i];
  return diff === 0;
}

export async function verifyPassword(
  password: string,
  encoded: string,
): Promise<boolean> {
  const parts = encoded.split("$");
  if (parts.length !== 4 || parts[0] !== ALGORITHM) return false;

  const iterations = Number.parseInt(parts[1], 10);
  if (!Number.isFinite(iterations) || iterations <= 0) return false;

  try {
    const expected = fromBase64(parts[3]);
    const actual = await derive(password, fromBase64(parts[2]), iterations);
    return timingSafeEqual(actual, expected);
  } catch {
    return false;
  }
}

export interface PasswordProblem {
  message: string;
}

/**
 * Deliberately a length floor and nothing else: composition rules push people
 * towards `Password1!` while making passphrases harder, so the only hard
 * requirement is enough material to make the PBKDF2 work worth doing.
 */
export function checkPasswordStrength(password: string): PasswordProblem | null {
  if (password.length < 10) {
    return { message: "Use at least 10 characters." };
  }
  if (password.length > 200) {
    return { message: "Use at most 200 characters." };
  }
  return null;
}
