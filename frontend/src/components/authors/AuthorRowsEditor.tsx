"use client";

import { useState } from "react";

import { INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { InstitutionPicker } from "@/components/authors/InstitutionPicker";
import { useLookup } from "@/components/authors/useLookup";
import { Button } from "@/components/ui/Button";
import { institutionForYear } from "@/services/affiliations";
import type { Affiliation, AuthorLookupResult, SubmissionAuthor } from "@/types/authors";

export interface SubmitterIdentity {
  slug: string;
  display_name: string;
  /** Display name, variants and the spellings already claimed, most used first. */
  names: string[];
  institution: string;
  affiliations: Affiliation[];
}

export function emptyAuthor(overrides: Partial<SubmissionAuthor> = {}): SubmissionAuthor {
  return {
    name: "",
    affiliation: "",
    institution: "",
    country_code: null,
    profile_slug: null,
    profile_display_name: null,
    is_submitter: false,
    ...overrides,
  };
}

/** The submitter's own row, pre-filled with the name and institution of the time. */
export function submitterRow(me: SubmitterIdentity, year: number | null): SubmissionAuthor {
  return emptyAuthor({
    name: me.names[0] ?? me.display_name,
    institution: institutionForYear(me.affiliations, year, me.institution),
    profile_slug: me.slug,
    profile_display_name: me.display_name,
    is_submitter: true,
  });
}

/**
 * Suggestions under an author name: verified profiles and the spellings the
 * dataset already prints. Choosing a printed spelling keeps this paper on the
 * same researcher page as that person's other papers; choosing a profile also
 * puts the paper on their verified profile once it is approved.
 */
function AuthorSuggestions({
  term,
  onPick,
}: {
  term: string;
  onPick: (pick: { name?: string; slug?: string | null; display_name?: string | null }) => void;
}) {
  const { data, loading } = useLookup<AuthorLookupResult>("authors", term, { minLength: 3 });
  if (!data && !loading) return null;
  const profiles = data?.profiles ?? [];
  const names = data?.names ?? [];
  if (!loading && profiles.length === 0 && names.length === 0) {
    return <p className="mt-1 text-body-sm text-muted">Not in ResearchLanka yet — that is fine for a new co-author.</p>;
  }
  return (
    <div className="mt-1 rounded border border-rule bg-surface p-2 text-body-sm">
      <p className="label-caps text-muted">Already in ResearchLanka</p>
      {loading && !data ? <p className="text-muted">Searching…</p> : null}
      <ul className="mt-1 flex flex-col gap-1">
        {profiles.map((profile) => (
          <li key={profile.slug}>
            <button
              type="button"
              onClick={() => onPick({ slug: profile.slug, display_name: profile.display_name })}
              className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-wash"
            >
              <span className="text-ink">
                <span aria-hidden className="mr-1 text-success-text">
                  ✓
                </span>
                {profile.display_name}
              </span>
              <span className="text-label text-muted">verified profile · {profile.institution}</span>
            </button>
          </li>
        ))}
        {names.map((option) => (
          <li key={option.name}>
            <button
              type="button"
              onClick={() =>
                onPick({
                  name: option.name,
                  slug: option.profile?.slug ?? undefined,
                  display_name: option.profile?.display_name ?? undefined,
                })
              }
              className="flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-wash"
            >
              <span className="text-ink">{option.name}</span>
              <span className="text-label text-muted">
                {option.publication_count} {option.publication_count === 1 ? "paper" : "papers"}
                {option.profile ? ` · ${option.profile.display_name}` : ""}
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Every author of a new publication, in order, each with the institution
 * they were at for it. The institution matters: it is what the publication
 * counts towards, and it is fixed per publication, so a later move does not
 * carry earlier work to the new institution.
 */
export function AuthorRowsEditor({
  rows,
  onChange,
  me,
  year,
  error,
}: {
  rows: SubmissionAuthor[];
  onChange: (rows: SubmissionAuthor[]) => void;
  me: SubmitterIdentity;
  year: number | null;
  error: { index: number | null; field: string | null; message: string } | null;
}) {
  const [searching, setSearching] = useState<number | null>(null);

  function update(index: number, patch: Partial<SubmissionAuthor>) {
    onChange(rows.map((row, position) => (position === index ? { ...row, ...patch } : row)));
  }

  function markMe(index: number) {
    onChange(
      rows.map((row, position) => {
        if (position === index) {
          const mine = me.names.some((name) => name.toLowerCase() === row.name.trim().toLowerCase());
          return {
            ...row,
            name: mine ? row.name : me.names[0] ?? me.display_name,
            institution: row.institution || institutionForYear(me.affiliations, year, me.institution),
            profile_slug: me.slug,
            profile_display_name: me.display_name,
            is_submitter: true,
          };
        }
        // Only one row can be the submitter; un-mark any other.
        return row.is_submitter ? { ...row, is_submitter: false, profile_slug: null, profile_display_name: null } : row;
      }),
    );
  }

  function move(index: number, offset: -1 | 1) {
    const target = index + offset;
    if (target < 0 || target >= rows.length) return;
    const next = [...rows];
    [next[index], next[target]] = [next[target], next[index]];
    onChange(next);
  }

  return (
    <div className="flex flex-col gap-3">
      <ol className="flex flex-col gap-3">
        {rows.map((row, index) => {
          const rowError = error && error.index === index ? error : null;
          const prefix = `author-${index}`;
          return (
            <li key={index} className={`rounded border p-3 ${rowError ? "border-critical" : "border-rule"}`}>
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="label-caps text-muted">Author {index + 1}</p>
                <div className="flex flex-wrap items-center gap-1">
                  <label className="mr-2 flex items-center gap-2 text-body-sm text-ink">
                    <input
                      type="radio"
                      name="submitter-row"
                      checked={row.is_submitter}
                      onChange={() => markMe(index)}
                    />
                    This is me
                  </label>
                  <Button type="button" variant="ghost" aria-label={`Move author ${index + 1} up`} disabled={index === 0} onClick={() => move(index, -1)}>
                    ↑
                  </Button>
                  <Button type="button" variant="ghost" aria-label={`Move author ${index + 1} down`} disabled={index === rows.length - 1} onClick={() => move(index, 1)}>
                    ↓
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    aria-label={`Remove author ${index + 1}`}
                    disabled={rows.length === 1}
                    onClick={() => onChange(rows.filter((_, position) => position !== index))}
                  >
                    ✕
                  </Button>
                </div>
              </div>

              <div className="mt-2 grid gap-3 md:grid-cols-2">
                <div>
                  <label htmlFor={`${prefix}-name`} className="label-caps text-muted">
                    Name as printed on the paper
                  </label>
                  <input
                    id={`${prefix}-name`}
                    value={row.name}
                    autoComplete="off"
                    onFocus={() => setSearching(index)}
                    onChange={(event) => {
                      setSearching(index);
                      // A renamed row is no longer the person it was linked to,
                      // unless it is the submitter's own row.
                      update(index, row.is_submitter ? { name: event.target.value } : { name: event.target.value, profile_slug: null, profile_display_name: null });
                    }}
                    className={`mt-1 ${INPUT_CLASS} ${inputBorder(Boolean(rowError && rowError.field !== "institution"))}`}
                  />
                  {row.is_submitter && me.names.length > 1 ? (
                    <div className="mt-1 flex flex-wrap gap-1">
                      {me.names.slice(0, 5).map((name) => (
                        <button
                          key={name}
                          type="button"
                          onClick={() => update(index, { name })}
                          className={`chip ${row.name === name ? "border-primary text-primary" : ""}`}
                        >
                          {name}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  {row.profile_slug ? (
                    <p className="mt-1 flex flex-wrap items-center gap-2 text-body-sm text-success-text">
                      ✓ {row.is_submitter ? "Your verified profile" : `Linked to ${row.profile_display_name ?? row.profile_slug}`}
                      {!row.is_submitter ? (
                        <button
                          type="button"
                          className="text-muted underline"
                          onClick={() => update(index, { profile_slug: null, profile_display_name: null })}
                        >
                          unlink
                        </button>
                      ) : null}
                    </p>
                  ) : null}
                  {searching === index && !row.is_submitter && !row.profile_slug ? (
                    <AuthorSuggestions
                      term={row.name}
                      onPick={(pick) => {
                        update(index, {
                          ...(pick.name ? { name: pick.name } : {}),
                          ...(pick.slug ? { profile_slug: pick.slug, profile_display_name: pick.display_name ?? null } : {}),
                          ...(!pick.name && !row.name && pick.display_name ? { name: pick.display_name } : {}),
                        });
                        setSearching(null);
                      }}
                    />
                  ) : null}
                </div>
                <div>
                  <label htmlFor={`${prefix}-institution`} className="label-caps text-muted">
                    Institution for this paper
                  </label>
                  <div className="mt-1">
                    <InstitutionPicker
                      id={`${prefix}-institution`}
                      value={row.institution}
                      invalid={Boolean(rowError && rowError.field === "institution")}
                      onChange={(label, option) =>
                        update(index, {
                          institution: label,
                          ...(option ? { country_code: option.sri_lankan ? "LK" : option.country_code } : {}),
                        })
                      }
                    />
                  </div>
                  <div className="mt-2 grid grid-cols-[1fr_6rem] gap-2">
                    <input
                      aria-label={`Author ${index + 1} department`}
                      placeholder="Department (optional)"
                      value={row.affiliation}
                      onChange={(event) => update(index, { affiliation: event.target.value })}
                      className={`${INPUT_CLASS} ${inputBorder(false)}`}
                    />
                    <input
                      aria-label={`Author ${index + 1} country code`}
                      placeholder="Country"
                      maxLength={2}
                      value={row.country_code ?? ""}
                      onChange={(event) => update(index, { country_code: event.target.value.toUpperCase() || null })}
                      className={`${INPUT_CLASS} ${inputBorder(Boolean(rowError && rowError.message.includes("country")))}`}
                    />
                  </div>
                </div>
              </div>
              {rowError ? (
                <p role="alert" className="mt-2 text-body-sm text-critical">
                  {rowError.message}
                </p>
              ) : null}
            </li>
          );
        })}
      </ol>
      <div>
        <Button type="button" variant="secondary" onClick={() => onChange([...rows, emptyAuthor()])}>
          Add an author
        </Button>
      </div>
    </div>
  );
}
