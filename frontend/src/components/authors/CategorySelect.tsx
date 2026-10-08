"use client";

import { Field, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import type { CategoryOption } from "@/types/authors";

/**
 * Field and subfield from the classifier taxonomy, the same entries Topics &
 * fields lists. Leaving the field blank lets OpenAlex (for a DOI) or the
 * category model decide; the administrator can still change it.
 */
export function CategorySelect({
  options,
  field,
  subfield,
  onChange,
  namePrefix = "",
  error,
  blankLabel = "Not sure — let the classifier choose",
}: {
  options: CategoryOption[];
  field: string;
  subfield: string;
  onChange: (field: string, subfield: string) => void;
  /** Lets the admin form post these as overrides without clashing with other inputs. */
  namePrefix?: string;
  error?: { field: string | null; message: string } | null;
  blankLabel?: string;
}) {
  const subfields = options.find((option) => option.field === field)?.subfields ?? [];
  const fieldError = error?.field === "primary_field" ? error.message : null;
  const subfieldError = error?.field === "primary_subfield" ? error.message : null;

  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Field id={`${namePrefix}primary_field`} label="Field" optional error={fieldError}>
        <select
          id={`${namePrefix}primary_field`}
          name={`${namePrefix}primary_field`}
          value={field}
          onChange={(event) => onChange(event.target.value, "")}
          className={`${INPUT_CLASS} ${inputBorder(Boolean(fieldError))}`}
        >
          <option value="">{blankLabel}</option>
          {options.map((option) => (
            <option key={option.field} value={option.field}>
              {option.field}
            </option>
          ))}
        </select>
      </Field>
      <Field id={`${namePrefix}primary_subfield`} label="Subfield" optional error={subfieldError}>
        <select
          id={`${namePrefix}primary_subfield`}
          name={`${namePrefix}primary_subfield`}
          value={subfield}
          disabled={!field}
          onChange={(event) => onChange(field, event.target.value)}
          className={`${INPUT_CLASS} ${inputBorder(Boolean(subfieldError))}`}
        >
          <option value="">{field ? "Any subfield" : "Choose a field first"}</option>
          {subfields.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </Field>
    </div>
  );
}
