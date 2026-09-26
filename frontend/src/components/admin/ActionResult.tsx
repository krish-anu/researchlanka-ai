"use client";

import { useFormStatus } from "react-dom";
import { Button } from "@/components/ui/Button";

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
  disabled = false,
}: {
  label: string;
  pendingLabel?: string;
  tone?: "primary" | "neutral" | "danger";
  name?: string;
  value?: string;
  disabled?: boolean;
}) {
  const { pending } = useFormStatus();

  
  return (
    <Button
      type="submit"
      name={name}
      value={value}
      variant={
        tone === "primary"
          ? "primary"
          : tone === "danger"
            ? "danger"
            : "secondary"
      }
      disabled={pending || disabled}
      loading={pending}
    >
      {pending ? pendingLabel : label}
    </Button>
  );
}
