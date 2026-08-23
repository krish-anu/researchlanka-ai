"use client";

import { useFormStatus } from "react-dom";

import type { ActionState } from "@/services/forms/state";

/**
 * Inline outcome line for an admin action.
 *
 * Errors take the serious tone rather than critical: a rejected merge or a
 * blocked role change is a refused operation, not a system fault, and the
 * critical red is reserved in this design system for things that are broken.
 */
export function ActionResult({ state }: { state: ActionState }) {
  if (state.status === "idle") return null;

  return (
    <p
      role="status"
      className={`mt-2 border-l-[3px] pl-3 text-body-sm ${
        state.status === "ok"
          ? "border-l-good text-success-text"
          : "border-l-serious text-serious"
      }`}
    >
      {state.message}
    </p>
  );
}

export function SubmitButton({
  label,
  pendingLabel = "Working…",
  tone = "neutral",
  name,
  value,
}: {
  label: string;
  pendingLabel?: string;
  tone?: "primary" | "neutral" | "danger";
  name?: string;
  value?: string;
}) {
  const { pending } = useFormStatus();

  const style =
    tone === "primary"
      ? "bg-primary text-on-primary hover:bg-primary-hover border-primary"
      : tone === "danger"
        ? "border-rule text-ink-secondary hover:border-critical hover:text-critical"
        : "border-rule text-ink-secondary hover:border-primary hover:text-primary";

  return (
    <button
      type="submit"
      name={name}
      value={value}
      disabled={pending}
      className={`rounded border px-3 py-1.5 text-body-sm font-medium transition-colors disabled:opacity-60 ${style}`}
    >
      {pending ? pendingLabel : label}
    </button>
  );
}
