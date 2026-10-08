"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";

import { submitAuthorApplicationAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { ClaimPicker, type ClaimDraft } from "@/components/authors/ClaimPicker";
import { Field, FormMessage, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";

export interface ApplicationDraft {
  display_name: string;
  name_variants: string;
  orcid: string;
  institution: string;
  department: string;
  position_title: string;
  application_note: string;
  claims: ClaimDraft[];
}

export const EMPTY_APPLICATION: ApplicationDraft = {
  display_name: "",
  name_variants: "",
  orcid: "",
  institution: "",
  department: "",
  position_title: "",
  application_note: "",
  claims: [],
};

/**
 * The author application, in all three of its modes.
 *
 * `sign-up` also creates the account (as pending), `account` applies from an
 * existing active account, `resubmit` revises an application an administrator
 * returned. Inputs are controlled so a rejected submission keeps everything
 * the applicant typed — React resets uncontrolled fields after a form action.
 */
export function ApplicationForm({
  mode,
  initial = EMPTY_APPLICATION,
}: {
  mode: "sign-up" | "account" | "resubmit";
  initial?: ApplicationDraft;
}) {
  const [state, formAction] = useActionState(submitAuthorApplicationAction, AUTHOR_FORM_IDLE);
  const [draft, setDraft] = useState<ApplicationDraft>(initial);
  const [email, setEmail] = useState("");

  const set = (field: keyof ApplicationDraft) => (
    event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => setDraft((current) => ({ ...current, [field]: event.target.value }));

  const fieldError = (name: string) => (state.status === "error" && state.field === name ? state.message : null);
  const generalError = state.status === "error" && !state.field;

  useEffect(() => {
    if (state.status !== "error" || !state.field) return;
    const target = state.field === "claims" ? "claim-search" : state.field;
    document.getElementById(target)?.focus();
  }, [state]);

  const names = [draft.display_name, ...draft.name_variants.split(/\r?\n/)].filter((name) => name.trim());

  return (
    <form action={formAction} className="flex flex-col gap-6">
      <input
        type="hidden"
        name="claims"
        value={JSON.stringify(
          draft.claims.map(({ publication_key, name_as_listed }) => ({ publication_key, name_as_listed })),
        )}
      />

      {generalError ? <FormMessage status="error" message={state.message} /> : null}

      {mode === "sign-up" ? (
        <fieldset className="flex flex-col gap-4">
          <legend className="mb-2 font-display text-h3 text-ink">Your account</legend>
          <Field id="email" label="Email" error={fieldError("email")} hint="Use your institutional address if you have one — administrators check it.">
            <input
              id="email"
              name="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              aria-invalid={Boolean(fieldError("email")) || undefined}
              className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("email")))}`}
            />
          </Field>
          <Field id="password" label="Password" error={fieldError("password")} hint="At least 10 characters.">
            <input
              id="password"
              name="password"
              type="password"
              required
              autoComplete="new-password"
              aria-invalid={Boolean(fieldError("password")) || undefined}
              className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("password")))}`}
            />
          </Field>
        </fieldset>
      ) : null}

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 font-display text-h3 text-ink">About you</legend>
        <Field id="display_name" label="Full name" error={fieldError("display_name")} hint="As you want it shown on your profile.">
          <input
            id="display_name"
            name="display_name"
            required
            autoComplete="name"
            value={draft.display_name}
            onChange={set("display_name")}
            aria-invalid={Boolean(fieldError("display_name")) || undefined}
            className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("display_name")))}`}
          />
        </Field>
        <Field
          id="name_variants"
          label="Other ways your name is printed"
          optional
          error={fieldError("name_variants")}
          hint="One per line, e.g. “Jayatilake, C” or “S.M.D.A.C. Jayatilake”. Helps match your papers."
        >
          <textarea
            id="name_variants"
            name="name_variants"
            rows={3}
            value={draft.name_variants}
            onChange={set("name_variants")}
            className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("name_variants")))}`}
          />
        </Field>
        <Field id="orcid" label="ORCID iD" optional error={fieldError("orcid")} hint="Strongly recommended: it is the clearest evidence that these papers are yours.">
          <input
            id="orcid"
            name="orcid"
            placeholder="0000-0002-1825-0097"
            value={draft.orcid}
            onChange={set("orcid")}
            className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("orcid")))}`}
          />
        </Field>
        <div className="grid gap-4 md:grid-cols-2">
          <Field id="institution" label="Institution" error={fieldError("institution")}>
            <input
              id="institution"
              name="institution"
              required
              value={draft.institution}
              onChange={set("institution")}
              className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("institution")))}`}
            />
          </Field>
          <Field id="department" label="Department" optional error={fieldError("department")}>
            <input
              id="department"
              name="department"
              value={draft.department}
              onChange={set("department")}
              className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("department")))}`}
            />
          </Field>
        </div>
        <Field id="position_title" label="Position" optional error={fieldError("position_title")} hint="e.g. Senior Lecturer, PhD candidate.">
          <input
            id="position_title"
            name="position_title"
            value={draft.position_title}
            onChange={set("position_title")}
            className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("position_title")))}`}
          />
        </Field>
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 font-display text-h3 text-ink">Your publications</legend>
        <p className="max-w-prose text-body-sm text-ink-secondary">
          Find the papers in the dataset that you wrote and pick your name in each author list.
          Administrators check every claim before it appears on your profile.
        </p>
        {fieldError("claims") ? (
          <p role="alert" className="text-body-sm text-critical">
            {fieldError("claims")}
            {typeof state.details?.title === "string" ? ` (“${state.details.title}”)` : null}
          </p>
        ) : null}
        <ClaimPicker
          value={draft.claims}
          onChange={(claims) => setDraft((current) => ({ ...current, claims }))}
          names={names}
          invalid={Boolean(fieldError("claims"))}
          onSpellingAdded={(spelling) =>
            setDraft((current) => {
              const known = [current.display_name, ...current.name_variants.split(/\r?\n/)].map((name) =>
                name.trim().toLowerCase(),
              );
              if (known.includes(spelling.trim().toLowerCase())) return current;
              const variants = current.name_variants.trim();
              return { ...current, name_variants: variants ? `${variants}\n${spelling}` : spelling };
            })
          }
        />
      </fieldset>

      <Field
        id="application_note"
        label="Anything the reviewer should know"
        optional
        error={fieldError("application_note")}
        hint="For example a staff page that lists you, or why a paper shows a different affiliation."
      >
        <textarea
          id="application_note"
          name="application_note"
          rows={3}
          maxLength={2000}
          value={draft.application_note}
          onChange={set("application_note")}
          className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError("application_note")))}`}
        />
      </Field>

      <div className="flex flex-col gap-3 border-t border-rule pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-prose text-body-sm text-muted">
          {mode === "sign-up"
            ? "Your account stays inactive until an administrator approves the application. You can sign in to check on it."
            : "An administrator reviews the application before anything appears publicly."}
        </p>
        <SubmitButton
          label={mode === "resubmit" ? "Resubmit application" : "Submit application"}
          pendingLabel="Submitting…"
          tone="primary"
        />
      </div>

      {mode === "sign-up" ? (
        <p className="text-body-sm text-ink-secondary">
          Already have an account?{" "}
          <Link href="/login?next=/register/author" className="text-primary underline">
            Sign in
          </Link>{" "}
          and apply from there.
        </p>
      ) : null}
    </form>
  );
}
