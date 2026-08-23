/**
 * Shared form-state shapes for `useActionState`.
 *
 * These live outside the action modules because a `"use server"` file may only
 * export async functions — a plain object constant exported alongside the
 * actions fails the build. Keeping the types here too means client components
 * can import them without pulling a server module into the browser bundle.
 */

export interface AuthFormState {
  error: string | null;
  /** Field the error belongs to, so the form can mark the right input. */
  field?: "email" | "password" | "name" | null;
}

export const EMPTY_FORM_STATE: AuthFormState = { error: null, field: null };

/** Outcome of a save, flag or triage action. */
export interface ActionState {
  status: "idle" | "ok" | "error";
  message: string;
}

export const IDLE: ActionState = { status: "idle", message: "" };
