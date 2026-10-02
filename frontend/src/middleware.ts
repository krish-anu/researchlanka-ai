/**
 * First-pass route gate.
 *
 * This is a fast redirect, not the security boundary — every protected page
 * also calls `requireCapability` in its own layout, which is what actually
 * enforces the rule. Doing it here as well means an unsigned visitor lands on
 * the sign-in form without the protected page rendering first.
 *
 * Only the signed/unsigned split happens here. The role in the session cookie
 * can be stale after an administrator promotes an account, so protected pages
 * enforce role capabilities against the live user store.
 */

import { NextResponse, type NextRequest } from "next/server";

import { readSessionToken, SESSION_COOKIE } from "@/services/auth/session";

const SIGNED_IN_ONLY = ["/account"];
const ADMIN_ONLY = ["/admin"];

function matches(pathname: string, prefixes: string[]): boolean {
  return prefixes.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export async function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl;
  const needsAdmin = matches(pathname, ADMIN_ONLY);
  const needsSession = needsAdmin || matches(pathname, SIGNED_IN_ONLY);
  if (!needsSession) return NextResponse.next();

  const user = await readSessionToken(
    request.cookies.get(SESSION_COOKIE)?.value,
  );

  if (!user) {
    const login = new URL("/login", request.url);
    login.searchParams.set("next", `${pathname}${search}`);
    return NextResponse.redirect(login);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/account/:path*", "/admin/:path*"],
};
