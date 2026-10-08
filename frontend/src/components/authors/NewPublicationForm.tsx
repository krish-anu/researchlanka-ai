"use client";

import Link from "next/link";
import { useActionState, useEffect, useRef, useState, useTransition } from "react";

import { lookupDoiAction, submitNewPublicationAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import {
  AuthorRowsEditor,
  emptyAuthor,
  submitterRow,
  type SubmitterIdentity,
} from "@/components/authors/AuthorRowsEditor";
import { CategorySelect } from "@/components/authors/CategorySelect";
import { Field, FormMessage, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { Button } from "@/components/ui/Button";
import { institutionForYear } from "@/services/affiliations";
import { likelyListedName } from "@/services/authorNames";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";
import { publicationHref } from "@/services/links";
import type { CategoryOption, DuplicateMatch, SubmissionAuthor } from "@/types/authors";

type TextField =
  | "doi"
  | "title"
  | "abstract"
  | "keywords"
  | "publication_year"
  | "publication_date"
  | "type"
  | "journal"
  | "publisher"
  | "volume"
  | "issue"
  | "first_page"
  | "last_page"
  | "language"
  | "url"
  | "pdf_url"
  | "note";

const EMPTY: Record<TextField, string> = {
  doi: "",
  title: "",
  abstract: "",
  keywords: "",
  publication_year: "",
  publication_date: "",
  type: "article",
  journal: "",
  publisher: "",
  volume: "",
  issue: "",
  first_page: "",
  last_page: "",
  language: "",
  url: "",
  pdf_url: "",
  note: "",
};

const LABEL: Record<TextField, string> = {
  doi: "DOI",
  title: "Title",
  abstract: "Abstract",
  keywords: "Keywords",
  publication_year: "Publication year",
  publication_date: "Publication date",
  type: "Publication type",
  journal: "Journal or venue",
  publisher: "Publisher",
  volume: "Volume",
  issue: "Issue",
  first_page: "First page",
  last_page: "Last page",
  language: "Language",
  url: "Link",
  pdf_url: "PDF link",
  note: "Note for the reviewer",
};

function Duplicates({ matches }: { matches: DuplicateMatch[] }) {
  return (
    <div role="alert" className="rounded border border-l-[3px] border-rule border-l-warning bg-surface p-3">
      <p className="text-body-sm font-medium text-ink">This publication is already in the dataset</p>
      <ul className="mt-2 flex flex-col gap-2">
        {matches.map((match) => (
          <li key={match.publication_key} className="text-body-sm text-ink-secondary">
            {match.is_public ? (
              <Link href={publicationHref(match.publication_key)} className="text-primary underline">
                {match.title ?? match.publication_key}
              </Link>
            ) : (
              <span className="text-ink">{match.title ?? match.publication_key}</span>
            )}
            {match.publication_year ? ` (${match.publication_year})` : ""}
            <span className="block text-muted">
              {match.is_public
                ? "It is public. Claim it from your author profile instead of adding it again."
                : `It is not public: ${match.hidden_reason ?? "it is held back by the dataset rules."} Flag it or contact an administrator if that is wrong.`}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/**
 * Add a publication the dataset is missing.
 *
 * DOI first: the backend fetches the record from OpenAlex or Crossref and
 * fills the form, and it repeats that lookup itself on submit so the evidence
 * the administrator sees did not come from this form. Without a DOI, every
 * field is typed by hand and a link is required so the paper can be checked.
 */
export function NewPublicationForm({
  me,
  publicationTypes,
  categories,
}: {
  me: SubmitterIdentity;
  publicationTypes: string[];
  categories: CategoryOption[];
}) {
  const [state, formAction] = useActionState(submitNewPublicationAction, AUTHOR_FORM_IDLE);
  const [values, setValues] = useState(EMPTY);
  const [authors, setAuthors] = useState<SubmissionAuthor[]>(() => [submitterRow(me, null)]);
  const [category, setCategory] = useState({ field: "", subfield: "" });
  const [categoryHint, setCategoryHint] = useState<string | null>(null);
  const [lookupMessage, setLookupMessage] = useState<string | null>(null);
  const [lookupDuplicates, setLookupDuplicates] = useState<DuplicateMatch[]>([]);
  const [lookupSource, setLookupSource] = useState<string | null>(null);
  const [looking, startLookup] = useTransition();

  // Errors on one author row carry its index; anything the form has no
  // input for is shown at the top instead of being lost.
  const rowIndex = typeof state.details?.index === "number" ? state.details.index : null;
  const rowError =
    state.status === "error" && (rowIndex !== null || state.field === "authors" || state.field === "your_author_name")
      ? { index: rowIndex ?? 0, field: state.field ?? null, message: state.message }
      : null;
  const categoryError =
    state.status === "error" && (state.field === "primary_field" || state.field === "primary_subfield")
      ? { field: state.field, message: state.message }
      : null;
  const errorField = rowError || categoryError ? null : state.field;
  const fieldKnown = Boolean(rowError || categoryError || (errorField && errorField in LABEL));

  useEffect(() => {
    if (state.status !== "error" || !fieldKnown) return;
    const target = rowError
      ? `author-${rowError.index}-${rowError.field === "institution" ? "institution" : "name"}`
      : categoryError
        ? categoryError.field ?? "primary_field"
        : `new-${errorField}`;
    document.getElementById(target)?.focus();
  }, [state, errorField, fieldKnown, rowError, categoryError]);

  const errorFor = (field: string) => (state.status === "error" && errorField === field ? state.message : null);
  const submitDuplicates = Array.isArray(state.details?.matches) ? (state.details.matches as DuplicateMatch[]) : [];
  const year = /^\d{4}$/.test(values.publication_year) ? Number(values.publication_year) : null;

  // The submitter's institution follows the publication year while it is
  // still the one filled in automatically: a 2019 paper goes under where they
  // were in 2019. Once they type their own, it is left alone.
  const autoInstitution = useRef(authors.find((author) => author.is_submitter)?.institution ?? "");
  useEffect(() => {
    const next = institutionForYear(me.affiliations, year, me.institution);
    // Read before updating the ref: the state updater runs later.
    const previous = autoInstitution.current;
    autoInstitution.current = next;
    if (previous === next) return;
    setAuthors((current) =>
      current.map((author) =>
        author.is_submitter && author.institution === previous ? { ...author, institution: next } : author,
      ),
    );
  }, [year, me.affiliations, me.institution]);

  function bind(field: TextField) {
    return {
      id: `new-${field}`,
      name: field,
      value: values[field],
      onChange: (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
        setValues((current) => ({ ...current, [field]: event.target.value })),
      "aria-invalid": Boolean(errorFor(field)) || undefined,
      className: `${INPUT_CLASS} ${inputBorder(Boolean(errorFor(field)))}`,
    };
  }

  function fetchDoi() {
    const doi = values.doi.trim();
    if (!doi) {
      setLookupMessage("Enter a DOI first.");
      return;
    }
    startLookup(async () => {
      const result = await lookupDoiAction(doi);
      if (!result.ok) {
        setLookupMessage(result.message);
        setLookupSource(null);
        setLookupDuplicates([]);
        return;
      }
      const { fields, duplicates, source } = result.data;
      setLookupDuplicates(duplicates);
      setLookupSource(source);
      setLookupMessage(null);
      setValues((current) => ({
        ...current,
        doi: result.data.doi,
        title: fields.title || current.title,
        abstract: fields.abstract || current.abstract,
        keywords: fields.keywords || current.keywords,
        publication_year: fields.publication_year ? String(fields.publication_year) : current.publication_year,
        publication_date: fields.publication_date ?? current.publication_date,
        type: publicationTypes.includes(fields.type) ? fields.type : current.type,
        journal: fields.journal || current.journal,
        publisher: fields.publisher || current.publisher,
        volume: fields.volume || current.volume,
        issue: fields.issue || current.issue,
        first_page: fields.first_page || current.first_page,
        last_page: fields.last_page || current.last_page,
        language: fields.language || current.language,
        url: fields.url || current.url,
        pdf_url: fields.pdf_url || current.pdf_url,
      }));
      if (fields.authors.length > 0) {
        // OpenAlex gives each author's institution for this paper; the
        // submitter's row is found by name and linked to their profile.
        const lookupYear = fields.publication_year ?? null;
        const mine = likelyListedName(fields.authors.map((author) => author.name), me.names);
        setAuthors(
          fields.authors.map((author) => {
            const isMe = author.name === mine;
            return emptyAuthor({
              name: author.name,
              affiliation: author.affiliation ?? "",
              institution:
                author.institution || (isMe ? institutionForYear(me.affiliations, lookupYear, me.institution) : ""),
              country_code: author.country_code || null,
              is_submitter: isMe,
              profile_slug: isMe ? me.slug : null,
              profile_display_name: isMe ? me.display_name : null,
            });
          }),
        );
      }
      const lookupField = result.data.category?.primary_field ?? "";
      const known = categories.find((option) => option.field === lookupField);
      if (known) {
        const subfield = result.data.category?.primary_subfield ?? "";
        setCategory({ field: known.field, subfield: known.subfields.includes(subfield) ? subfield : "" });
        setCategoryHint("Category filled from OpenAlex. Change it if it is wrong.");
      }
    });
  }

  return (
    <form action={formAction} className="flex flex-col gap-6">
      <input type="hidden" name="authors" value={JSON.stringify(authors.filter((author) => author.name.trim()))} />

      {state.status === "error" && !fieldKnown && submitDuplicates.length === 0 ? (
        <FormMessage status="error" message={state.message} />
      ) : null}
      {submitDuplicates.length > 0 ? <Duplicates matches={submitDuplicates} /> : null}

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 font-display text-h3 text-ink">Start from the DOI</legend>
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <div className="flex-1">
            <Field id="new-doi" label="DOI" optional error={errorFor("doi")} hint="Leave empty for a paper without one, and fill the form by hand.">
              <input placeholder="10.1234/abcd.5678" {...bind("doi")} />
            </Field>
          </div>
          <Button type="button" variant="secondary" loading={looking} onClick={fetchDoi} className="sm:mb-7">
            Fetch details
          </Button>
        </div>
        {lookupMessage ? <p className="text-body-sm text-serious">{lookupMessage}</p> : null}
        {lookupSource && lookupDuplicates.length === 0 ? (
          <p className="text-body-sm text-success-text">
            Details filled from {lookupSource === "openalex" ? "OpenAlex" : "Crossref"}. Check them before sending.
          </p>
        ) : null}
        {lookupDuplicates.length > 0 ? <Duplicates matches={lookupDuplicates} /> : null}
      </fieldset>

      <fieldset className="flex flex-col gap-4">
        <legend className="mb-2 font-display text-h3 text-ink">The publication</legend>
        <Field id="new-title" label={LABEL.title} error={errorFor("title")}>
          <input required {...bind("title")} />
        </Field>
        <Field
          id="new-abstract"
          label={LABEL.abstract}
          error={errorFor("abstract")}
          hint="The full abstract. The AI relevance check reads the title and abstract."
        >
          <textarea rows={8} required {...bind("abstract")} />
        </Field>
        <Field id="new-keywords" label={LABEL.keywords} optional error={errorFor("keywords")} hint="Separate with semicolons.">
          <input {...bind("keywords")} />
        </Field>
        <div className="grid gap-4 md:grid-cols-3">
          <Field id="new-publication_year" label={LABEL.publication_year} error={errorFor("publication_year")}>
            <input type="number" inputMode="numeric" min={1950} required {...bind("publication_year")} />
          </Field>
          <Field id="new-publication_date" label={LABEL.publication_date} optional error={errorFor("publication_date")}>
            <input type="date" {...bind("publication_date")} />
          </Field>
          <Field id="new-type" label={LABEL.type} error={errorFor("type")}>
            <select {...bind("type")}>
              {publicationTypes.map((type) => (
                <option key={type} value={type}>
                  {type.replace(/-/g, " ")}
                </option>
              ))}
            </select>
          </Field>
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          {(["journal", "publisher", "volume", "issue", "first_page", "last_page", "language"] as TextField[]).map((field) => (
            <Field key={field} id={`new-${field}`} label={LABEL[field]} optional error={errorFor(field)}>
              <input {...bind(field)} />
            </Field>
          ))}
        </div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field id="new-url" label={LABEL.url} optional={Boolean(values.doi.trim())} error={errorFor("url")} hint="Required when there is no DOI.">
            <input type="url" inputMode="url" {...bind("url")} />
          </Field>
          <Field id="new-pdf_url" label={LABEL.pdf_url} optional error={errorFor("pdf_url")}>
            <input type="url" inputMode="url" {...bind("pdf_url")} />
          </Field>
        </div>
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 font-display text-h3 text-ink">Authors, in order</legend>
        <p className="max-w-prose text-body-sm text-ink-secondary">
          Add every author with the institution they were at for this paper. Link authors who are
          already in ResearchLanka so the paper joins their other work, and mark which one is you.
        </p>
        <AuthorRowsEditor rows={authors} onChange={setAuthors} me={me} year={year} error={rowError} />
      </fieldset>

      <fieldset className="flex flex-col gap-3">
        <legend className="mb-2 font-display text-h3 text-ink">Category</legend>
        <p className="max-w-prose text-body-sm text-ink-secondary">
          Where the paper is listed under Topics &amp; fields.
          {categoryHint ? ` ${categoryHint}` : " Leave it blank and the field classifier suggests one for the reviewer."}
        </p>
        <CategorySelect
          options={categories}
          field={category.field}
          subfield={category.subfield}
          onChange={(field, subfield) => {
            setCategory({ field, subfield });
            setCategoryHint(null);
          }}
          error={categoryError}
        />
      </fieldset>

      <Field id="new-note" label={LABEL.note} optional hint="Anything that helps confirm the paper is AI research led from Sri Lanka.">
        <textarea rows={3} maxLength={1000} {...bind("note")} />
      </Field>

      <div className="flex flex-col gap-3 border-t border-rule pt-4 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-prose text-body-sm text-muted">
          The paper is checked by the AI relevance model when you send it. An administrator then
          confirms it is AI research and Sri Lanka-led before it enters the dataset.
        </p>
        <SubmitButton label="Send for review" pendingLabel="Checking and sending…" tone="primary" />
      </div>
    </form>
  );
}
