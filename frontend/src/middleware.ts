/**
 * First-pass route gate.
 *
 * This is a fast redirect, not the security boundary — every protected page
 * also calls `requireCapability` in its own layout, which is what actually
 * enforces the rule. Doing it here as well means an unsigned visitor lands on
 * the sign-in form without the protected page rendering first.
 *
 * Only the signed/unsigned split and the admin-role check happen here, since
 * both are readable straight from the session cookie. Anything needing the user
 * store stays in the layouts.
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

  if (needsAdmin && user.role !== "admin") {
    const forbidden = new URL("/forbidden", request.url);
    forbidden.searchParams.set("need", "admin.access");
    return NextResponse.redirect(forbidden);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/account/:path*", "/admin/:path*"],
};
