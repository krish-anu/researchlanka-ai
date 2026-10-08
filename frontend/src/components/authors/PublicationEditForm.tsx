"use client";

import { useActionState, useEffect, useState } from "react";

import { proposePublicationEditAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { Field, FormMessage, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";
import type { EditableField } from "@/types/authors";

const LONG_FIELDS = new Set<EditableField>(["title", "abstract", "keywords"]);
const PAIRED_FIELDS: EditableField[][] = [
  ["journal", "publisher"],
  ["volume", "issue"],
  ["first_page", "last_page"],
  ["publication_year", "type"],
  ["language"],
  ["url", "pdf_url"],
];

function asText(value: string | number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

/**
 * Suggest corrections to one publication.
 *
 * Every field is posted with the value it was shown with, and the server
 * sends only the ones that changed. Changed fields are marked as the author
 * types, so they can see exactly what the reviewer will be asked to approve.
 */
export function PublicationEditForm({
  publicationKey,
  values,
  labels,
  publicationTypes,
}: {
  publicationKey: string;
  values: Partial<Record<EditableField, string | number | null>>;
  labels: Record<EditableField, string>;
  publicationTypes: string[];
}) {
  const [state, formAction] = useActionState(proposePublicationEditAction, AUTHOR_FORM_IDLE);
  const original = Object.fromEntries(
    (Object.keys(labels) as EditableField[]).map((field) => [field, asText(values[field])]),
  ) as Record<EditableField, string>;
  const [draft, setDraft] = useState(original);
  const changed = (Object.keys(labels) as EditableField[]).filter(
    (field) => draft[field].trim() !== original[field].trim(),
  );

  const erroredField = state.field?.startsWith("field:") ? state.field.slice(6) : null;
  const fieldKnown = Boolean(erroredField && erroredField in labels);

  useEffect(() => {
    if (state.status === "error" && fieldKnown) document.getElementById(`field-${erroredField}`)?.focus();
  }, [state, erroredField, fieldKnown]);

  const errorFor = (field: EditableField) =>
    state.status === "error" && state.field === `field:${field}` ? state.message : null;

  function input(field: EditableField) {
    const common = {
      id: `field-${field}`,
      name: `field:${field}`,
      value: draft[field],
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
        setDraft((current) => ({ ...current, [field]: event.target.value })),
      "aria-invalid": Boolean(errorFor(field)) || undefined,
      className: `${INPUT_CLASS} ${inputBorder(Boolean(errorFor(field)))} ${
        changed.includes(field) ? "bg-wash" : ""
      }`,
    };
    if (field === "abstract") return <textarea rows={8} {...common} />;
    if (field === "type") {
      return (
        <select {...common}>
          {!publicationTypes.includes(draft.type) && draft.type ? <option value={draft.type}>{draft.type}</option> : null}
          {publicationTypes.map((type) => (
            <option key={type} value={type}>
              {type.replace(/-/g, " ")}
            </option>
          ))}
        </select>
      );
    }
    if (field === "publication_year") return <input type="number" inputMode="numeric" min={1950} {...common} />;
    if (field === "url" || field === "pdf_url") return <input type="url" inputMode="url" {...common} />;
    return <input {...common} />;
  }

  function field(name: EditableField) {
    return (
      <Field
        key={name}
        id={`field-${name}`}
        label={labels[name]}
        error={errorFor(name)}
        hint={changed.includes(name) ? `Was: ${original[name] || "empty"}` : undefined}
      >
        {input(name)}
        <input type="hidden" name={`original:${name}`} value={original[name]} />
      </Field>
    );
  }

  return (
    <form action={formAction} className="flex flex-col gap-4">
      <input type="hidden" name="publication_key" value={publicationKey} />
      {state.status === "error" && !fieldKnown ? (
        <FormMessage status="error" message={state.message} />
      ) : null}

      {(Object.keys(labels) as EditableField[]).filter((name) => LONG_FIELDS.has(name)).map(field)}
      {PAIRED_FIELDS.map((pair) => (
        <div key={pair.join("-")} className="grid gap-4 md:grid-cols-2">
          {pair.map(field)}
        </div>
      ))}

      <Field
        id="note"
        label="Note for the reviewer"
        optional
        hint="Where the correct value comes from helps, e.g. the publisher's page."
      >
        <textarea id="note" name="note" rows={3} maxLength={1000} className={`${INPUT_CLASS} ${inputBorder(false)}`} />
      </Field>

      <div className="flex flex-wrap items-center justify-between gap-3 border-t border-rule pt-4">
        <p className="text-body-sm text-muted">
          {changed.length === 0
            ? "Nothing changed yet."
            : `${changed.length} ${changed.length === 1 ? "field" : "fields"} changed: ${changed
                .map((name) => labels[name].toLowerCase())
                .join(", ")}.`}
        </p>
        <SubmitButton label="Send for review" pendingLabel="Sending…" tone="primary" disabled={changed.length === 0} />
      </div>
    </form>
  );
}
