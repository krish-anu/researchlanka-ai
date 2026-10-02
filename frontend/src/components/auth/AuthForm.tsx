"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";
import { useFormStatus } from "react-dom";
import { EyeIcon, EyeOffIcon } from "@/components/layout/NavIcons";
import { Button } from "@/components/ui/Button";

import { EMPTY_FORM_STATE, type AuthFormState } from "@/services/forms/state";

function SubmitButton({ label }: { label: string }) {
  const { pending } = useFormStatus();

  return (
    <Button
      type="submit"
      variant="primary"
      size="md"
      loading={pending}
      className="w-full"
    >
      {label}
    </Button>
  );
}

function Field({
  name,
  label,
  type = "text",
  autoComplete,
  invalid,
  hint,
  error,
}: {
  name: string;
  label: string;
  type?: string;
  autoComplete?: string;
  invalid: boolean;
  hint?: string;
  error?: string | null;
}) {
  const [visible, setVisible] = useState(false);
  const hintId = hint ? `${name}-hint` : undefined;
  const errorId = error ? `${name}-error` : undefined;
  const describedBy = [errorId, hintId].filter(Boolean).join(" ") || undefined;
  const inputType = type === "password" && visible ? "text" : type;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={name} className="label-caps text-muted">
        {label}
      </label>
      <div
        className={`flex items-center rounded border bg-surface focus-within:ring-2 focus-within:ring-primary/30 focus-within:ring-offset-2 focus-within:ring-offset-page ${
          invalid ? "border-critical" : "border-rule"
        }`}
      >
        <input
          id={name}
          name={name}
          type={inputType}
          required
          autoComplete={autoComplete}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          className="min-h-11 w-full flex-1 bg-transparent px-3 py-2 text-body-md text-ink outline-none placeholder:text-muted"
        />
        {type === "password" ? (
          <button
            type="button"
            className="icon-control text-ink-secondary"
            aria-pressed={visible}
            aria-label={visible ? "Hide password" : "Show password"}
            onClick={() => setVisible((value) => !value)}
          >
            {visible ? <EyeOffIcon /> : <EyeIcon />}
          </button>
        ) : null}
      </div>
      {error ? (
        <p id={errorId} role="alert" className="text-body-sm text-critical">
          {error}
        </p>
      ) : null}
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
  const fieldError = (name: "name" | "email" | "password") =>
    state.field === name ? state.error : null;

  useEffect(() => {
    if (!state.field || !state.error) return;
    document.getElementById(state.field)?.focus();
  }, [state]);

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <input type="hidden" name="next" value={next} />

      {state.error && !state.field ? (
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
          error={fieldError("name")}
        />
      ) : null}

      <Field
        name="email"
        label="Email"
        type="email"
        autoComplete="email"
        invalid={state.field === "email"}
        error={fieldError("email")}
      />

      <Field
        name="password"
        label="Password"
        type="password"
        autoComplete={isSignUp ? "new-password" : "current-password"}
        invalid={state.field === "password"}
        error={fieldError("password")}
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
