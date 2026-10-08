import type { ReactNode } from "react";

/** Matches the inputs on the admin cards and the sign-in form. */
export const INPUT_CLASS =
  "min-h-11 w-full rounded border bg-surface px-3 py-2 text-body-sm text-ink placeholder:text-muted focus:outline-none focus-visible:ring-2 focus-visible:ring-primary/30";

export function inputBorder(invalid: boolean): string {
  return invalid ? "border-critical" : "border-rule";
}

/**
 * Label, hint and error around one input.
 *
 * The input itself is passed in, because the forms here mix controlled
 * inputs, textareas and selects; this only owns the wording around them.
 */
export function Field({
  id,
  label,
  hint,
  error,
  optional = false,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string | null;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="label-caps text-muted">
        {label}
        {optional ? <span className="ml-1 normal-case tracking-normal text-muted">(optional)</span> : null}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-body-sm text-critical">
          {error}
        </p>
      ) : null}
      {hint ? (
        <p id={`${id}-hint`} className="text-body-sm text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Form-level outcome line, for errors that belong to no single field. */
export function FormMessage({
  status,
  message,
}: {
  status: "idle" | "ok" | "error";
  message: string;
}) {
  if (status === "idle" || !message) return null;
  return (
    <p
      role={status === "error" ? "alert" : "status"}
      className={`rounded border border-l-[3px] border-rule bg-surface px-3 py-2 text-body-sm ${
        status === "ok" ? "border-l-good text-success-text" : "border-l-critical text-ink-secondary"
      }`}
    >
      {message}
    </p>
  );
}
