/**
 * Issue and clear the session cookie.
 *
 * Kept out of `app/actions/*`: every async function exported from a
 * `"use server"` file becomes an endpoint the browser can call, and one that
 * starts a session for an arbitrary user record would let anyone sign in as
 * anyone. Server actions import these instead.
 */

import { cookies } from "next/headers";

import {
  createSessionToken,
  SESSION_COOKIE,
  SESSION_MAX_AGE_SECONDS,
  sessionCookieOptions,
} from "@/services/auth/session";
import { publicUser, type UserRecord } from "@/types/auth";

export async function startSession(user: UserRecord): Promise<void> {
  const token = await createSessionToken(publicUser(user));
  const store = await cookies();
  store.set(SESSION_COOKIE, token, sessionCookieOptions(SESSION_MAX_AGE_SECONDS));
}

export async function endSession(): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", sessionCookieOptions(0));
}
