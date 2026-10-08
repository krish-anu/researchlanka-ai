"use client";

import Link from "next/link";
import { useActionState, useState } from "react";

import { decideAuthorContributionAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { EvidenceChip, NameMatchChip } from "@/components/admin/AuthorEvidence";
import { CategorySelect } from "@/components/authors/CategorySelect";
import { FormMessage, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { StatusBadge } from "@/components/authors/StatusBadge";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";
import { formatDate } from "@/services/format";
import { authorProfileHref, publicationHref } from "@/services/links";
import {
  CONTRIBUTION_STATUS_LABEL,
  CONTRIBUTION_TYPE_LABEL,
  type CategoryOption,
  type EditableField,
  type NewPublicationProposal,
  type ReviewedContribution,
} from "@/types/authors";

const FIELD_LABEL: Record<EditableField, string> = {
  title: "Title",
  abstract: "Abstract",
  keywords: "Keywords",
  publication_year: "Year",
  type: "Type",
  journal: "Journal or venue",
  publisher: "Publisher",
  volume: "Volume",
  issue: "Issue",
  first_page: "First page",
  last_page: "Last page",
  language: "Language",
  url: "Link",
  pdf_url: "PDF link",
};

function show(value: unknown): string {
  return value === null || value === undefined || value === "" ? "—" : String(value);
}

function EditDiff({ contribution }: { contribution: ReviewedContribution }) {
  // In form order: the proposal arrives as JSONB, whose key order is not the form's.
  const fields = (Object.keys(FIELD_LABEL) as EditableField[]).filter((field) => field in contribution.proposed);
  const stale = new Set(contribution.stale_fields ?? []);
  return (
    <div className="overflow-x-auto">
      {stale.size > 0 ? (
        <p className="mb-2 text-body-sm text-serious">
          The pipeline changed {stale.size === 1 ? "this field" : "these fields"} since the author
          proposed the edit: {[...stale].map((field) => FIELD_LABEL[field].toLowerCase()).join(", ")}. Compare
          before approving.
        </p>
      ) : null}
      <table className="w-full min-w-[32rem] border-collapse text-body-sm">
        <thead>
          <tr className="border-b border-rule text-left">
            <th className="label-caps py-2 pr-3 text-muted">Field</th>
            <th className="label-caps py-2 pr-3 text-muted">Public now</th>
            <th className="label-caps py-2 text-muted">Proposed</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((field) => (
            <tr key={field} className="border-b border-rule align-top">
              <th scope="row" className="py-2 pr-3 text-left font-medium text-ink">
                {FIELD_LABEL[field]}
                {stale.has(field) ? <span className="ml-1 text-serious">*</span> : null}
              </th>
              <td className="max-w-[24rem] whitespace-pre-line break-words py-2 pr-3 text-ink-secondary">
                {show(contribution.current?.[field])}
              </td>
              <td className="max-w-[24rem] whitespace-pre-line break-words py-2 text-ink">
                {show((contribution.proposed as Record<string, unknown>)[field])}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function NewPublicationEvidence({ contribution }: { contribution: ReviewedContribution }) {
  const proposed = contribution.proposed as NewPublicationProposal;
  const classifier = contribution.classifier;
  const ownership = contribution.lookup_evidence.ownership ?? {};
  const label = classifier.label ?? "review";

  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="font-display text-body-lg text-ink">{proposed.title}</p>
        <p className="text-body-sm text-muted">
          {[proposed.publication_year, proposed.type?.replace(/-/g, " "), proposed.journal].filter(Boolean).join(" · ")}
        </p>
        <p className="mt-1 flex flex-wrap gap-3 text-body-sm">
          {proposed.doi ? (
            <a href={`https://doi.org/${proposed.doi}`} target="_blank" rel="noopener noreferrer" className="data-mono text-primary underline">
              doi:{proposed.doi}
            </a>
          ) : (
            <span className="text-muted">No DOI</span>
          )}
          {proposed.url ? (
            <a href={proposed.url} target="_blank" rel="noopener noreferrer nofollow" className="text-primary underline">
              Open link
            </a>
          ) : null}
        </p>
      </div>

      <div>
        <p className="label-caps text-muted">Authors and the institution each was at for this paper</p>
        <ol className="mt-1 flex flex-col gap-1 text-body-sm">
          {proposed.authors.map((author, index) => {
            const submitter = author.is_submitter || author.name === proposed.your_author_name;
            return (
              <li key={`${author.name}-${index}`} className="flex flex-wrap items-baseline gap-x-2">
                <span className="data-mono text-muted">{index + 1}.</span>
                <span className={submitter ? "font-medium text-ink" : "text-ink-secondary"}>{author.name}</span>
                <span className="text-muted">
                  — {author.institution || "no institution"}
                  {author.country_code ? ` (${author.country_code})` : ""}
                  {author.affiliation ? `, ${author.affiliation}` : ""}
                </span>
                {submitter ? <EvidenceChip tone="neutral">submitter</EvidenceChip> : null}
                {!submitter && author.profile_slug ? (
                  <Link href={authorProfileHref(author.profile_slug)} target="_blank">
                    <EvidenceChip tone="warn">
                      linked to {author.profile_display_name ?? author.profile_slug}; gets this on their profile
                    </EvidenceChip>
                  </Link>
                ) : null}
              </li>
            );
          })}
        </ol>
        <div className="mt-1">
          <NameMatchChip match={contribution.name_match} />
        </div>
      </div>

      <CategoryEvidence contribution={contribution} />

      <details className="rounded border border-rule p-3">
        <summary className="cursor-pointer text-body-sm text-ink">Abstract</summary>
        <p className="mt-2 whitespace-pre-line text-body-sm text-ink-secondary">{proposed.abstract}</p>
      </details>

      <div className="grid gap-3 md:grid-cols-2">
        <section className="rounded border border-rule p-3">
          <p className="label-caps text-muted">AI relevance check</p>
          {classifier.available === false ? (
            <p className="mt-1 text-body-sm text-serious">
              The model was not available ({show(classifier.reason)}). Decide from the title and abstract.
            </p>
          ) : (
            <>
              <p className="mt-1 flex items-center gap-2">
                <EvidenceChip tone={label === "AI" ? "good" : label === "non-AI" ? "bad" : "warn"}>
                  Model says {label === "review" ? "needs review" : label}
                </EvidenceChip>
                <span className="data-mono text-body-sm text-muted">score {show(classifier.confidence)}</span>
              </p>
              {classifier.reason ? <p className="mt-1 text-body-sm text-muted">{classifier.reason}</p> : null}
            </>
          )}
        </section>
        <section className="rounded border border-rule p-3">
          <p className="label-caps text-muted">
            Source record ({contribution.lookup_source === "manual" ? "none — entered by hand" : contribution.lookup_source})
          </p>
          {contribution.lookup_source === "manual" ? (
            <p className="mt-1 text-body-sm text-ink-secondary">
              No OpenAlex or Crossref record, so there is no automatic Sri Lanka-ownership evidence. Check the
              affiliations above and the link.
            </p>
          ) : (
            <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 text-body-sm">
              <dt className="text-muted">Ownership</dt>
              <dd className="text-ink">
                {show(ownership.ownership_decision)} ({show(ownership.ownership_confidence)})
              </dd>
              <dt className="text-muted">Reason</dt>
              <dd className="text-ink-secondary">{show(ownership.ownership_reason)}</dd>
              <dt className="text-muted">Institutions</dt>
              <dd className="text-ink-secondary">{show(contribution.lookup_evidence.institutions)}</dd>
              <dt className="text-muted">Countries</dt>
              <dd className="text-ink-secondary">{show(contribution.lookup_evidence.countries)}</dd>
            </dl>
          )}
        </section>
      </div>

      {contribution.duplicates && contribution.duplicates.length > 0 ? (
        <div className="rounded border border-l-[3px] border-rule border-l-serious p-3">
          <p className="text-body-sm font-medium text-ink">Now matches an existing record</p>
          <ul className="mt-1 text-body-sm text-ink-secondary">
            {contribution.duplicates.map((match) => (
              <li key={match.publication_key}>
                <Link href={publicationHref(match.publication_key)} target="_blank" className="text-primary underline">
                  {match.title ?? match.publication_key}
                </Link>
                {match.is_public ? " (public)" : ` (hidden: ${match.hidden_reason})`}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function CategoryEvidence({ contribution }: { contribution: ReviewedContribution }) {
  const proposed = contribution.proposed as NewPublicationProposal;
  const lookup = contribution.lookup_evidence.category ?? {};
  const model = contribution.classifier.category;
  const rows: { source: string; value: string }[] = [];
  if (proposed.primary_field) {
    rows.push({ source: "Chosen by the author", value: [proposed.primary_field, proposed.primary_subfield].filter(Boolean).join(" › ") });
  }
  if (lookup.primary_field) {
    rows.push({ source: "OpenAlex", value: [lookup.primary_field, lookup.primary_subfield].filter(Boolean).join(" › ") });
  }
  if (model?.available && model.field) {
    rows.push({ source: "Field classifier", value: [model.field, model.subfield].filter(Boolean).join(" › ") });
  }
  return (
    <section className="rounded border border-rule p-3">
      <p className="label-caps text-muted">Category</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-body-sm text-serious">No category from any source. Choose one below before approving.</p>
      ) : (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-body-sm">
          {rows.map((row) => (
            <div key={row.source} className="contents">
              <dt className="text-muted">{row.source}</dt>
              <dd className="text-ink">{row.value}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className="mt-1 text-body-sm text-muted">The first of these is used unless you choose otherwise.</p>
    </section>
  );
}

/**
 * One author contribution with the decision controls.
 *
 * A new publication needs the same two judgements every harvested record
 * gets — is it AI research, is it Sri Lanka-led — so both are explicit
 * controls rather than implied by the approve button.
 */
export function AuthorContributionCard({
  contribution,
  categories,
}: {
  contribution: ReviewedContribution;
  categories: CategoryOption[];
}) {
  const [state, formAction] = useActionState(decideAuthorContributionAction, AUTHOR_FORM_IDLE);
  const [aiDecision, setAiDecision] = useState<"" | "AI" | "NON_AI">("");
  const [override, setOverride] = useState({ field: "", subfield: "" });
  const isNew = contribution.contribution_type === "new_publication";
  const open = contribution.status === "pending" && state.status !== "ok";
  const modelSaysAI = contribution.classifier.label === "AI";

  return (
    <article className={`panel border-l-[3px] p-5 ${open ? "border-l-warning" : "border-l-rule"}`}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="label-caps text-muted">{CONTRIBUTION_TYPE_LABEL[contribution.contribution_type]}</p>
          {!isNew && contribution.publication_key ? (
            <Link href={publicationHref(contribution.publication_key)} target="_blank" className="font-display text-body-lg text-ink hover:text-primary hover:underline">
              {contribution.publication_title ?? contribution.publication_key}
            </Link>
          ) : null}
          <p className="text-body-sm text-muted">
            From{" "}
            <Link href={authorProfileHref(contribution.profile.slug)} target="_blank" className="text-primary underline">
              {contribution.profile.display_name}
            </Link>
            {contribution.profile.institution ? ` (${contribution.profile.institution})` : ""} ·{" "}
            {formatDate(contribution.created_at)}
          </p>
        </div>
        <StatusBadge status={contribution.status} label={CONTRIBUTION_STATUS_LABEL[contribution.status]} />
      </header>

      <div className="mt-4 border-t border-rule pt-4">
        {isNew ? <NewPublicationEvidence contribution={contribution} /> : <EditDiff contribution={contribution} />}
        {contribution.author_note ? (
          <p className="mt-3 text-body-sm text-ink-secondary">
            <span className="text-muted">Author&apos;s note: </span>
            {contribution.author_note}
          </p>
        ) : null}
        {contribution.decision_reason ? (
          <p className="mt-3 text-body-sm text-ink-secondary">
            <span className="text-muted">Decision: </span>
            {contribution.decision_reason} — {contribution.decided_by}, {formatDate(contribution.decided_at)}
          </p>
        ) : null}
      </div>

      {open ? (
        <form action={formAction} className="mt-4 flex flex-col gap-3 border-t border-rule pt-4">
          <input type="hidden" name="contribution_id" value={contribution.contribution_id} />
          <input type="hidden" name="record_version" value={contribution.record_version} />

          {isNew ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="label-caps text-muted">Before approving</legend>
              <div className="flex flex-wrap gap-4 text-body-sm text-ink">
                <label className="flex items-center gap-2">
                  <input type="radio" name="ai_decision" value="AI" checked={aiDecision === "AI"} onChange={() => setAiDecision("AI")} />
                  This is AI research
                </label>
                <label className="flex items-center gap-2">
                  <input type="radio" name="ai_decision" value="NON_AI" checked={aiDecision === "NON_AI"} onChange={() => setAiDecision("NON_AI")} />
                  This is not AI research
                </label>
              </div>
              <label className="flex items-center gap-2 text-body-sm text-ink">
                <input type="checkbox" name="ownership_verified" className="h-4 w-4" />
                I checked that this publication is Sri Lanka-led
              </label>
              {aiDecision === "AI" && !modelSaysAI ? (
                <p className="text-body-sm text-serious">
                  The model did not label this AI. Give a reason for accepting it.
                </p>
              ) : null}
              {aiDecision === "NON_AI" ? (
                <p className="text-body-sm text-muted">Not AI research: reject it below and tell the author why.</p>
              ) : null}
            </fieldset>
          ) : null}

          {isNew ? (
            <fieldset className="flex flex-col gap-2">
              <legend className="label-caps text-muted">Change the category (optional)</legend>
              <CategorySelect
                options={categories}
                field={override.field}
                subfield={override.subfield}
                onChange={(field, subfield) => setOverride({ field, subfield })}
                namePrefix="override_"
                blankLabel="Keep the category above"
                error={
                  state.status === "error" && (state.field === "primary_field" || state.field === "primary_subfield")
                    ? { field: state.field, message: state.message }
                    : null
                }
              />
            </fieldset>
          ) : null}

          <label className="flex flex-col gap-1.5">
            <span className="label-caps text-muted">Message to the author</span>
            <textarea
              name="reason"
              rows={2}
              maxLength={1000}
              placeholder={isNew ? "Required to reject, or to accept against the model." : "Required to reject."}
              className={`${INPUT_CLASS} ${inputBorder(state.status === "error" && state.field === "reason")}`}
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <SubmitButton
              name="decision"
              value="approve"
              label={isNew ? "Approve and add to the dataset" : "Approve correction"}
              tone="primary"
              disabled={isNew && aiDecision !== "AI"}
            />
            <SubmitButton name="decision" value="reject" label="Reject" tone="danger" />
          </div>
        </form>
      ) : null}
      <FormMessage status={state.status} message={state.message} />
    </article>
  );
}
