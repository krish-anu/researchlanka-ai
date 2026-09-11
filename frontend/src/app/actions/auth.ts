"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { checkCredentials, createUser, recordSignIn } from "@/services/auth/store";
import { checkPasswordStrength } from "@/services/auth/password";
import {
  createSessionToken,
  SESSION_COOKIE,
  SESSION_MAX_AGE_SECONDS,
  sessionCookieOptions,
  sessionSecretProblem,
} from "@/services/auth/session";
import type { AuthFormState } from "@/services/forms/state";
import { publicUser } from "@/types/auth";

/**
 * Only same-origin paths are honoured as a post-sign-in destination, so a
 * crafted `?next=https://evil.example` cannot turn the sign-in form into an
 * open redirect. `//host` is rejected too — the browser reads it as protocol-
 * relative and would leave the site.
 */
function safeNext(value: FormDataEntryValue | null): string {
  const candidate = typeof value === "string" ? value : "";
  if (!candidate.startsWith("/") || candidate.startsWith("//")) return "/";
  return candidate;
}

async function startSession(user: Parameters<typeof publicUser>[0]) {
  const token = await createSessionToken(publicUser(user));
  const store = await cookies();
  store.set(
    SESSION_COOKIE,
    token,
    sessionCookieOptions(SESSION_MAX_AGE_SECONDS),
  );
}

export async function signIn(
  _state: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const email = String(formData.get("email") ?? "");
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  if (!email || !password) {
    return { error: "Enter your email and password.", field: "email" };
  }

  // Checked before the password, not after: there is no point verifying
  // credentials the server cannot then issue a session for.
  const misconfigured = sessionSecretProblem();
  if (misconfigured) return { error: misconfigured };

  const check = await checkCredentials(email, password);

  if (!check.ok) {
    // The same message for "no such account" and "wrong password": telling the
    // two apart lets anyone test which addresses are registered here.
    return {
      error:
        check.reason === "disabled"
          ? "This account has been suspended. Contact a platform administrator."
          : "Email or password is incorrect.",
      field: "password",
    };
  }

  await recordSignIn(check.user.id);
  await startSession(check.user);
  redirect(next);
}

export async function signUp(
  _state: AuthFormState,
  formData: FormData,
): Promise<AuthFormState> {
  const name = String(formData.get("name") ?? "").trim();
  const email = String(formData.get("email") ?? "").trim();
  const password = String(formData.get("password") ?? "");
  const next = safeNext(formData.get("next"));

  const misconfigured = sessionSecretProblem();
  if (misconfigured) return { error: misconfigured };

  if (!name) return { error: "Enter your name.", field: "name" };
  if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return { error: "Enter a valid email address.", field: "email" };
  }

  const weak = checkPasswordStrength(password);
  if (weak) return { error: weak.message, field: "password" };

  // Self-registration only ever creates the `user` role. Administrators are
  // promoted from /admin/users by an existing administrator, never claimed.
  const created = await createUser({ name, email, password, role: "user" });

  if (!created.ok) {
    return {
      error: "An account already exists for that email address.",
      field: "email",
    };
  }

  await startSession(created.user);
  redirect(next);
}

export async function signOut(): Promise<void> {
  const store = await cookies();
  store.set(SESSION_COOKIE, "", sessionCookieOptions(0));
  redirect("/");
}
