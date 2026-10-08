"use client";

import { useActionState, useEffect, useState } from "react";

import { updateAuthorProfileAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { AffiliationHistoryEditor } from "@/components/authors/AffiliationHistoryEditor";
import { Field, FormMessage, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";
import { PROFILE_LINK_LABEL, type AuthorProfile, type ProfileLinks } from "@/types/authors";

const LINK_FIELDS = Object.keys(PROFILE_LINK_LABEL) as (keyof ProfileLinks)[];

const LINK_PLACEHOLDER: Record<keyof ProfileLinks, string> = {
  website_url: "https://",
  google_scholar_url: "https://scholar.google.com/citations?user=…",
  researchgate_url: "https://www.researchgate.net/profile/…",
  linkedin_url: "https://www.linkedin.com/in/…",
};

/**
 * The parts of a profile that are the author's own words. These save
 * straight to the public profile; name, institution and ORCID are what the
 * administrator verified, so they are shown but not editable here.
 */
export function ProfileEditor({ profile }: { profile: AuthorProfile }) {
  const [state, formAction] = useActionState(updateAuthorProfileAction, AUTHOR_FORM_IDLE);
  const [values, setValues] = useState({
    bio: profile.bio,
    position_title: profile.position_title,
    department: profile.department,
    ...Object.fromEntries(LINK_FIELDS.map((field) => [field, profile.links[field] ?? ""])),
  } as Record<string, string>);

  useEffect(() => {
    if (state.status === "error" && state.field) document.getElementById(state.field)?.focus();
  }, [state]);

  const fieldError = (name: string) => (state.status === "error" && state.field === name ? state.message : null);
  const bind = (name: string) => ({
    id: name,
    name,
    value: values[name] ?? "",
    onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setValues((current) => ({ ...current, [name]: event.target.value })),
    "aria-invalid": Boolean(fieldError(name)) || undefined,
    className: `${INPUT_CLASS} ${inputBorder(Boolean(fieldError(name)))}`,
  });

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <dl className="grid gap-x-6 gap-y-2 rounded border border-rule p-3 text-body-sm sm:grid-cols-[auto_1fr]">
        <dt className="text-muted">Name</dt>
        <dd className="text-ink">{profile.display_name}</dd>
        <dt className="text-muted">Institution</dt>
        <dd className="text-ink">{profile.institution}</dd>
        <dt className="text-muted">ORCID iD</dt>
        <dd className="data-mono text-ink">{profile.orcid ?? "—"}</dd>
        <dd className="text-muted sm:col-span-2">
          These were verified with your application. Ask an administrator to change them.
        </dd>
      </dl>

      <Field id="bio" label="Bio" optional error={fieldError("bio")} hint="Up to 2,000 characters. Shown on your public profile.">
        <textarea rows={5} maxLength={2000} {...bind("bio")} />
      </Field>
      <div className="grid gap-4 md:grid-cols-2">
        <Field id="position_title" label="Position" optional error={fieldError("position_title")}>
          <input {...bind("position_title")} />
        </Field>
        <Field id="department" label="Department" optional error={fieldError("department")}>
          <input {...bind("department")} />
        </Field>
      </div>
      <fieldset className="flex flex-col gap-2">
        <legend className="label-caps mb-1 text-muted">Affiliation history</legend>
        <p className="max-w-prose text-body-sm text-muted">
          Each publication keeps counting for the institution on the paper. Your history decides
          which institution your profile shows for each period.
        </p>
        {state.status === "error" && state.field === "affiliations" ? (
          <p role="alert" className="text-body-sm text-critical">
            {state.message}
          </p>
        ) : null}
        <AffiliationHistoryEditor
          initial={profile.affiliations ?? []}
          errorIndex={
            state.status === "error" && state.field === "affiliations" && typeof state.details?.index === "number"
              ? state.details.index
              : null
          }
        />
      </fieldset>

      <div className="grid gap-4 md:grid-cols-2">
        {LINK_FIELDS.map((field) => (
          <Field key={field} id={field} label={PROFILE_LINK_LABEL[field]} optional error={fieldError(field)}>
            <input type="url" inputMode="url" placeholder={LINK_PLACEHOLDER[field]} {...bind(field)} />
          </Field>
        ))}
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <SubmitButton label="Save profile" pendingLabel="Saving…" tone="primary" />
        <FormMessage status={state.status} message={state.status === "error" && state.field ? "" : state.message} />
      </div>
    </form>
  );
}
