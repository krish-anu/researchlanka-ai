"use client";

import Link from "next/link";
import { useActionState } from "react";

import { decideAuthorApplicationAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { EMAIL_KIND_LABEL, EvidenceChip, NameMatchChip } from "@/components/admin/AuthorEvidence";
import { FormMessage, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { StatusBadge } from "@/components/authors/StatusBadge";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";
import { formatDate } from "@/services/format";
import { publicationHref } from "@/services/links";
import { PROFILE_STATUS_LABEL, type ApplicationReview } from "@/types/authors";

/**
 * One author application and the evidence for it.
 *
 * Nothing here proves identity — the email is not verified in this round —
 * so the card puts the signals side by side: does the name match each listed
 * author, does the ORCID iD appear on the papers, is the email an
 * institutional address, is anyone else claiming the same listed author.
 */
export function AuthorApplicationCard({ application }: { application: ApplicationReview }) {
  const [state, formAction] = useActionState(decideAuthorApplicationAction, AUTHOR_FORM_IDLE);
  const { evidence, claims } = application;
  const open = application.status === "pending";
  const emailTone =
    evidence.email.kind === "academic" || evidence.email.kind === "sri_lankan_organisation"
      ? "good"
      : evidence.email.kind === "free_webmail"
        ? "warn"
        : "neutral";

  return (
    <article className={`panel border-l-[3px] p-5 ${open ? "border-l-warning" : "border-l-rule"}`}>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-display text-body-lg text-ink">{application.display_name}</p>
          <p className="text-body-sm text-ink-secondary">
            {[application.position_title, application.department, application.institution].filter(Boolean).join(" · ")}
          </p>
          <p className="mt-1 text-body-sm text-muted">Submitted {formatDate(application.submitted_at)}</p>
        </div>
        <StatusBadge status={application.status} label={PROFILE_STATUS_LABEL[application.status]} />
      </header>

      <dl className="mt-4 grid gap-x-6 gap-y-2 border-t border-rule pt-4 text-body-sm sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted">Email</dt>
        <dd className="flex flex-wrap items-center gap-2">
          <span className="data-mono text-ink">{application.user_email}</span>
          <EvidenceChip tone={emailTone}>{EMAIL_KIND_LABEL[evidence.email.kind]}</EvidenceChip>
          <EvidenceChip tone="neutral">Not verified</EvidenceChip>
        </dd>
        <dt className="text-muted">ORCID iD</dt>
        <dd className="flex flex-wrap items-center gap-2">
          {application.orcid ? (
            <>
              <a href={`https://orcid.org/${application.orcid}`} target="_blank" rel="noopener noreferrer" className="data-mono text-primary underline">
                {application.orcid}
              </a>
              <EvidenceChip tone={evidence.orcid_matches > 0 ? "good" : "neutral"}>
                On {evidence.orcid_matches} of {claims.length} claimed records
              </EvidenceChip>
              {evidence.orcid_held_by.length > 0 ? (
                <EvidenceChip tone="bad">Already used by {evidence.orcid_held_by.join(", ")}</EvidenceChip>
              ) : null}
            </>
          ) : (
            <span className="text-muted">Not given</span>
          )}
        </dd>
        {application.name_variants.length > 0 ? (
          <>
            <dt className="text-muted">Also printed as</dt>
            <dd className="text-ink">{application.name_variants.join("; ")}</dd>
          </>
        ) : null}
        {application.application_note ? (
          <>
            <dt className="text-muted">Applicant&apos;s note</dt>
            <dd className="whitespace-pre-line text-ink">{application.application_note}</dd>
          </>
        ) : null}
        {application.decision_reason ? (
          <>
            <dt className="text-muted">Last decision</dt>
            <dd className="text-ink">
              {application.decision_reason}
              <span className="text-muted"> — {application.decided_by}, {formatDate(application.decided_at)}</span>
            </dd>
          </>
        ) : null}
      </dl>

      <form action={formAction} className="mt-4 flex flex-col gap-4 border-t border-rule pt-4">
        <input type="hidden" name="profile_id" value={application.profile_id} />
        <input type="hidden" name="record_version" value={application.record_version} />

        <div>
          <p className="label-caps text-muted">Claimed publications ({claims.length})</p>
          {claims.length === 0 ? (
            <p className="mt-1 text-body-sm text-muted">None. The applicant can claim publications after approval.</p>
          ) : (
            <ul className="mt-2 flex flex-col divide-y divide-rule rounded border border-rule">
              {claims.map((claim) => (
                <li key={claim.claim_id} className="flex flex-col gap-2 p-3 md:flex-row md:items-start md:justify-between">
                  <div className="min-w-0">
                    <Link href={publicationHref(claim.publication_key)} className="text-body-sm text-ink hover:text-primary hover:underline" target="_blank">
                      {claim.publication.title ?? claim.publication_key}
                    </Link>
                    <p className="text-body-sm text-muted">
                      {claim.publication.publication_year ?? "—"} · listed as <span className="text-ink">{claim.name_as_listed}</span>
                      {claim.author_position ? ` (author ${claim.author_position})` : ""}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-1.5">
                      <NameMatchChip match={claim.evidence.name_match} />
                      {claim.evidence.orcid_match ? <EvidenceChip tone="good">ORCID on record</EvidenceChip> : null}
                      {!claim.evidence.still_listed ? <EvidenceChip tone="bad">Name no longer on the record</EvidenceChip> : null}
                      {claim.evidence.competing_claims.map((competing) => (
                        <EvidenceChip key={competing.claim_id} tone="bad">
                          Also claimed by {competing.display_name} ({competing.status})
                        </EvidenceChip>
                      ))}
                    </div>
                  </div>
                  {open && claim.status === "pending" ? (
                    <label className="flex shrink-0 items-center gap-2 text-body-sm text-ink-secondary">
                      <input type="checkbox" name="reject_claim" value={claim.claim_id} className="h-4 w-4" />
                      Don&apos;t accept this claim
                    </label>
                  ) : (
                    <span className="label-caps text-muted">{claim.status}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {open ? (
          <>
            <label className="flex flex-col gap-1.5">
              <span className="label-caps text-muted">Message to the applicant</span>
              <textarea
                name="reason"
                rows={2}
                maxLength={1000}
                placeholder="Required to reject or ask for changes; it is shown to the applicant."
                className={`${INPUT_CLASS} ${inputBorder(state.status === "error" && state.field === "reason")}`}
              />
            </label>
            <div className="flex flex-wrap gap-2">
              <SubmitButton name="decision" value="approve" label="Approve" tone="primary" />
              <SubmitButton name="decision" value="request_changes" label="Ask for changes" />
              <SubmitButton name="decision" value="reject" label="Reject" tone="danger" />
            </div>
          </>
        ) : null}
        <FormMessage status={state.status} message={state.message} />
      </form>
    </article>
  );
}
