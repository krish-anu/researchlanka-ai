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
import { findUserById } from "@/services/auth/store";
import {
  accountStatus,
  GUEST,
  type AccountStatus,
  type SessionUser,
  type Viewer,
} from "@/types/auth";

/** Where a signed-in account that is not active yet is sent instead of a sign-in form. */
export const APPLICATION_STATUS_PATH = "/register/author/status";

/**
 * The current viewer, always defined — an absent or invalid cookie resolves to
 * the `guest` role rather than `null`.
 */
export async function getViewer(): Promise<Viewer> {
  const store = await cookies();
  const user = await readSessionToken(store.get(SESSION_COOKIE)?.value);
  if (!user) return GUEST;

  let current = null;
  try {
    current = await findUserById(user.id);
  } catch (error) {
    console.warn("[auth] Could not resolve session user from the account store", error);
    return GUEST;
  }

  if (!current || current.disabled) return GUEST;

  const sessionUser: SessionUser = {
    id: current.id,
    email: current.email,
    name: current.name,
    role: current.role,
  };
  const status = accountStatus(current);
  if (status !== "active") {
    return { role: "guest", user: null, applicant: { ...sessionUser, status } };
  }
  return { role: sessionUser.role, user: sessionUser };
}

/**
 * The signed-in account whatever its status, for the screens that serve
 * applicants as well as active accounts (the author application and its
 * status page). Everything else should use `requireUser`/`requireCapability`.
 */
export async function requireAccount(
  returnTo: string,
): Promise<{ user: SessionUser; status: AccountStatus }> {
  const viewer = await getViewer();
  if (viewer.user) return { user: viewer.user, status: "active" };
  if (viewer.applicant) {
    const { status, ...user } = viewer.applicant;
    return { user, status };
  }
  redirect(`/login?next=${encodeURIComponent(returnTo)}`);
}

/** An applicant is signed in already; a sign-in form would be a dead end. */
function redirectUnsigned(viewer: Viewer, returnTo: string): never {
  if (!viewer.user && viewer.applicant) redirect(APPLICATION_STATUS_PATH);
  redirect(`/login?next=${encodeURIComponent(returnTo)}`);
}

export async function getSessionUser(): Promise<SessionUser | null> {
  return (await getViewer()).user;
}

/** Send an unsigned visitor to sign in, returning them here afterwards. */
export async function requireUser(returnTo: string): Promise<SessionUser> {
  const viewer = await getViewer();
  if (!viewer.user) redirectUnsigned(viewer, returnTo);
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
  if (!viewer.user) redirectUnsigned(viewer, returnTo);
  if (!can(viewer.role, capability)) {
    redirect(`/forbidden?need=${encodeURIComponent(capability)}`);
  }
  return viewer.user;
}

/** Capability check for the current viewer, for conditional rendering. */
export async function viewerCan(capability: Capability): Promise<boolean> {
  return can((await getViewer()).role, capability);
}
