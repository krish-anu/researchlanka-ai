"use client";

import { useId, useState } from "react";

import { INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { useLookup } from "@/components/authors/useLookup";
import type { InstitutionOption } from "@/types/authors";

/**
 * An institution name with suggestions from the registry and the dataset.
 *
 * Picking a suggestion writes the exact label institution rankings count, so
 * the publication lands on the right institution page. Typing a name that is
 * not suggested is still allowed — a foreign co-author's university may not
 * be in the dataset yet.
 */
export function InstitutionPicker({
  id,
  value,
  onChange,
  invalid = false,
  placeholder = "Start typing, e.g. Moratuwa",
}: {
  id: string;
  value: string;
  onChange: (label: string, option: InstitutionOption | null) => void;
  invalid?: boolean;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const { data, loading } = useLookup<InstitutionOption[]>("institutions", open ? value : "");
  const listId = useId();
  const options = data ?? [];

  return (
    <div className="relative">
      <input
        id={id}
        role="combobox"
        aria-expanded={open && options.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoComplete="off"
        value={value}
        placeholder={placeholder}
        onChange={(event) => {
          onChange(event.target.value, null);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        // Delay so a click on a suggestion lands before the list closes.
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        aria-invalid={invalid || undefined}
        className={`${INPUT_CLASS} ${inputBorder(invalid)}`}
      />
      {open && (options.length > 0 || loading) ? (
        <ul
          id={listId}
          role="listbox"
          className="panel absolute left-0 right-0 z-30 mt-1 max-h-64 overflow-y-auto p-1 text-body-sm"
        >
          {loading && options.length === 0 ? <li className="px-2 py-1.5 text-muted">Searching…</li> : null}
          {options.map((option) => (
            <li key={option.label} role="option" aria-selected={option.label === value}>
              <button
                type="button"
                onMouseDown={(event) => event.preventDefault()}
                onClick={() => {
                  onChange(option.label, option);
                  setOpen(false);
                }}
                className="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left hover:bg-wash"
              >
                <span className="text-ink">{option.label}</span>
                <span className="shrink-0 text-label text-muted">
                  {option.sri_lankan ? "Sri Lanka" : option.country_code ?? ""}
                  {option.publication_count ? ` · ${option.publication_count} papers` : ""}
                </span>
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
