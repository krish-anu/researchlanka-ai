"use client";

import Link from "next/link";
import { useActionState } from "react";
import { useFormStatus } from "react-dom";

import { EMPTY_FORM_STATE, type AuthFormState } from "@/services/forms/state";

function SubmitButton({ label }: { label: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="w-full rounded bg-primary px-4 py-2.5 text-body-sm font-semibold text-on-primary transition-colors hover:bg-primary-hover disabled:opacity-60"
    >
      {pending ? "Working…" : label}
    </button>
  );
}

function Field({
  name,
  label,
  type = "text",
  autoComplete,
  invalid,
  hint,
}: {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  invalid: boolean;
  hint?: string;
}) {
  const hintId = hint ? `${name}-hint` : undefined;
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="label-caps text-muted">
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        required
        autoComplete={autoComplete}
        aria-invalid={invalid || undefined}
        aria-describedby={hintId}
        className={`rounded border bg-surface px-3 py-2 text-body-md text-ink placeholder:text-muted ${
          invalid ? "border-critical" : "border-rule"
        }`}
      />
      {hint ? (
        <p id={hintId} className="text-body-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

interface AuthFormProps {
  action: (state: AuthFormState, formData: FormData) => Promise<AuthFormState>;
  mode: "sign-in" | "sign-up";
  next: string;
}

/**
 * Shared shell for sign-in and registration.
 *
 * `useActionState` keeps the server action's error next to the field it belongs
 * to without the form losing what was typed, so a failed sign-in does not make
 * the reader start over.
 */
export function AuthForm({ action, mode, next }: AuthFormProps) {
  const [state, formAction] = useActionState(action, EMPTY_FORM_STATE);
  const isSignUp = mode === "sign-up";

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />

      {state.error ? (
        <p
          role="alert"
          className="rounded border border-l-[3px] border-rule border-l-critical bg-surface px-3 py-2 text-body-sm text-ink-secondary"
        >
          {state.error}
        </p>
      ) : null}

      {isSignUp ? (
        <Field
          name="name"
          label="Name"
          autoComplete="name"
          invalid={state.field === "name"}
        />
      ) : null}

      <Field
        name="email"
        label="Email"
        type="email"
        autoComplete="email"
        invalid={state.field === "email"}
      />

      <Field
        name="password"
        label="Password"
        type="password"
        autoComplete={isSignUp ? "new-password" : "current-password"}
        invalid={state.field === "password"}
        hint={isSignUp ? "At least 10 characters." : undefined}
      />

      <SubmitButton label={isSignUp ? "Create account" : "Sign in"} />

      <p className="text-center text-body-sm text-ink-secondary">
        {isSignUp ? "Already have an account? " : "No account yet? "}
        <Link
          href={{
            pathname: isSignUp ? "/login" : "/register",
            query: next === "/" ? undefined : { next },
          }}
          className="text-primary underline"
        >
          {isSignUp ? "Sign in" : "Create one"}
        </Link>
      </p>
    </form>
  );
}
