"use client";

import Link from "next/link";
import { useActionState } from "react";

import { decideAuthorClaimAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { EvidenceChip, NameMatchChip } from "@/components/admin/AuthorEvidence";
import { FormMessage, INPUT_CLASS, inputBorder } from "@/components/authors/FormFields";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";
import { formatDate } from "@/services/format";
import { authorProfileHref, publicationHref } from "@/services/links";
import type { ReviewedClaim } from "@/types/authors";

/** A publication claimed by an author who is already approved. */
export function AuthorClaimCard({ claim }: { claim: ReviewedClaim }) {
  const [state, formAction] = useActionState(decideAuthorClaimAction, AUTHOR_FORM_IDLE);
  const decided = state.status === "ok";

  return (
    <article className="panel border-l-[3px] border-l-warning p-4">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <Link href={publicationHref(claim.publication_key)} target="_blank" className="font-display text-body-lg text-ink hover:text-primary hover:underline">
            {claim.publication.title ?? claim.publication_key}
          </Link>
          <p className="text-body-sm text-muted">
            Claimed {formatDate(claim.created_at)} by{" "}
            {claim.profile?.slug ? (
              <Link href={authorProfileHref(claim.profile.slug)} target="_blank" className="text-primary underline">
                {claim.profile.display_name}
              </Link>
            ) : (
              claim.profile?.display_name
            )}
            {claim.profile?.institution ? ` (${claim.profile.institution})` : ""} · listed as{" "}
            <span className="text-ink">{claim.name_as_listed}</span>
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
      </div>

      {decided ? (
        <FormMessage status="ok" message={state.message} />
      ) : (
        <form action={formAction} className="mt-3 flex flex-col gap-2 border-t border-rule pt-3 md:flex-row md:items-end">
          <input type="hidden" name="claim_id" value={claim.claim_id} />
          <label className="flex flex-1 flex-col gap-1.5">
            <span className="label-caps text-muted">Reason (needed to reject)</span>
            <input
              name="reason"
              maxLength={1000}
              className={`${INPUT_CLASS} ${inputBorder(state.status === "error" && state.field === "reason")}`}
            />
          </label>
          <div className="flex gap-2">
            <SubmitButton name="decision" value="approved" label="Approve" tone="primary" />
            <SubmitButton name="decision" value="rejected" label="Reject" tone="danger" />
          </div>
        </form>
      )}
      {state.status === "error" ? <FormMessage status="error" message={state.message} /> : null}
    </article>
  );
}
