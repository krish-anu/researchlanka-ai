/**
 * Server-side viewer resolution and route guards.
 *
 * Import only from server components, server actions and route handlers — it
 * reads the session cookie through `next/headers`.
 */

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { can, type Capability } from "@/services/auth/permissions";
import { readSessionToken, SESSION_COOKIE } from "@/services/auth/session";
import { GUEST, type SessionUser, type Viewer } from "@/types/auth";

/**
 * The current viewer, always defined — an absent or invalid cookie resolves to
 * the `guest` role rather than `null`.
 */
export async function getViewer(): Promise<Viewer> {
  const store = await cookies();
  const user = await readSessionToken(store.get(SESSION_COOKIE)?.value);
  return user ? { role: user.role, user } : GUEST;
}

export async function getSessionUser(): Promise<SessionUser | null> {
  return (await getViewer()).user;
}

/** Send an unsigned visitor to sign in, returning them here afterwards. */
export async function requireUser(returnTo: string): Promise<SessionUser> {
  const viewer = await getViewer();
  if (!viewer.user) {
    redirect(`/login?next=${encodeURIComponent(returnTo)}`);
  }
  return viewer.user;
}

/**
 * Require a capability.
 *
 * An unsigned visitor is sent to sign in — they may well have the right role
 * behind a cookie they have not presented. A signed-in user who simply lacks
 * the capability is sent to /forbidden instead, because signing in again would
 * not help and a sign-in form would be a dead end.
 */
export async function requireCapability(
  capability: Capability,
  returnTo: string,
): Promise<SessionUser> {
  const viewer = await getViewer();
  if (!viewer.user) {
    redirect(`/login?next=${encodeURIComponent(returnTo)}`);
  }
  if (!can(viewer.role, capability)) {
    redirect(`/forbidden?need=${encodeURIComponent(capability)}`);
  }
  return viewer.user;
}

/** Capability check for the current viewer, for conditional rendering. */
export async function viewerCan(capability: Capability): Promise<boolean> {
  return can((await getViewer()).role, capability);
}
