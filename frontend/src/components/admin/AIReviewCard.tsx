"use client";

import { useActionState } from "react";

import { decideAIReviewAction, retryAIReviewSyncAction } from "@/app/actions/admin";
import { ActionResult, SubmitButton } from "@/components/admin/ActionResult";
import { Button } from "@/components/ui/Button";
import { SourceBadge } from "@/components/ui/Provenance";
import { IDLE } from "@/services/forms/state";
import type { AIReviewCandidate } from "@/services/workspace/types";

function text(value: string | number | null | undefined): string {
  return value === null || value === undefined || value === "" ? "n/a" : String(value);
}

function statusLabel(status: AIReviewCandidate["review_status"]): string {
  return status.replace("_", " ");
}

export function AIReviewCard({ candidate }: { candidate: AIReviewCandidate }) {
  const [state, formAction] = useActionState(decideAIReviewAction, IDLE);
  const [syncState, retryAction] = useActionState(retryAIReviewSyncAction, IDLE);
  const pending = candidate.review_status === "pending_review";
  const publication = candidate.publication;

  return (
    <article className={`panel border-l-[3px] border-l-machine p-4 ${pending ? "" : "opacity-80"}`}>
      <header className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b border-rule pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="label-caps text-machine">Model output</span>
          {pending ? <span className="label-caps text-primary">Needs decision</span> : null}
          <span className="data-mono text-ink-secondary">
            {statusLabel(candidate.review_status)} · v{candidate.record_version}
          </span>
          <span className="data-mono text-muted">
            sync {candidate.sync_status}
          </span>
        </div>
        {candidate.decision_timestamp ? (
          <span className="label-caps text-muted">
            {text(candidate.decided_by.name || candidate.decided_by.email)} · {text(candidate.decision_timestamp)}
          </span>
        ) : null}
      </header>

      <div className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center gap-2">
          <SourceBadge source={publication.source_dataset || "publication"} />
          <span className="data-mono text-muted">{candidate.publication_key}</span>
          <span className="text-body-sm text-ink-secondary">
            {text(publication.publication_year ?? publication.publication_date)}
          </span>
        </div>

        <div>
          <h2 className="font-display text-h3 text-ink">
            {publication.title || "Untitled publication"}
          </h2>
          <p className="mt-1 data-mono break-all text-body-sm text-muted">
            {publication.doi ? (
              <a
                href={publication.doi.startsWith("http") ? publication.doi : `https://doi.org/${publication.doi.replace(/^doi:/i, "")}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline"
              >
                {publication.doi}
              </a>
            ) : (
              "No DOI"
            )}
            {" · "}
            OpenAlex {text(publication.openalex_id)}
          </p>
          {publication.url ? (
            <a className="text-body-sm text-primary underline" href={publication.url}>
              Source link
            </a>
          ) : null}
        </div>

        <dl className="grid gap-3 text-body-sm md:grid-cols-3">
          <Info label="Authors" value={publication.authors} />
          <Info label="Affiliations" value={publication.author_affiliations || publication.institutions} />
          <Info label="Sri Lanka evidence" value={publication.sri_lankan_institutions || publication.countries} />
          <Info label="Keywords" value={publication.keywords} />
          <Info label="Venue" value={publication.journal || publication.publisher} />
          <Info label="Type" value={publication.type} />
        </dl>

        <p className="max-h-40 overflow-y-auto border-t border-rule pt-3 text-body-sm text-ink-secondary">
          {publication.abstract || "No abstract available."}
        </p>

        <section className="rounded-md border border-rule bg-wash p-3">
          <h3 className="label-caps text-machine">Gemini classification</h3>
          <dl className="grid gap-3 md:grid-cols-3">
            <Info label="Prediction" value={candidate.gemini.label} />
            <Info
              label="Confidence"
              value={
                candidate.gemini.confidence ||
                candidate.gemini.normalized_confidence
              }
            />
            <Info label="Model" value={candidate.gemini.model} />
            <div className="md:col-span-3">
              <p className="label-caps text-muted">Reasoning</p>
              <p className="mt-1 text-ink-secondary">
                {candidate.gemini.reason || "n/a"}
              </p>
            </div>
          </dl>
        </section>
      </div>

      {pending ? (
        <form action={formAction} className="mt-4 flex flex-col gap-3 border-t border-rule pt-4">
          <input type="hidden" name="publication_key" value={candidate.publication_key} />
          <input type="hidden" name="record_version" value={candidate.record_version} />
          <label className="flex flex-col gap-1 text-body-sm text-ink-secondary">
            Reviewer notes
            <textarea
              name="note"
              rows={3}
              className="min-h-11 rounded border border-rule bg-surface px-3 py-2 text-ink focus-visible:border-primary"
              placeholder="Required when rejecting"
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <SubmitButton
              name="decision"
              value="human_accepted"
              label="Accept as AI"
              tone="primary"
            />
            <SubmitButton
              name="decision"
              value="human_rejected"
              label="Reject as Non-AI"
              tone="danger"
              className="sm:ml-auto"
            />
          </div>
        </form>
      ) : (
        <div className="mt-4 border-t border-rule pt-3 text-body-sm text-ink-secondary">
          <p>{candidate.reviewer_notes || "No reviewer notes recorded."}</p>
        </div>
      )}

      {candidate.sync_status === "failed" ? (
        <form action={retryAction} className="mt-3 flex flex-wrap items-center gap-2">
          <input type="hidden" name="publication_key" value={candidate.publication_key} />
          <Button type="submit" variant="secondary">
            Retry Sync
          </Button>
          <span className="text-body-sm text-critical">{candidate.last_sync_error}</span>
        </form>
      ) : null}

      <ActionResult state={state} />
      <ActionResult state={syncState} />
    </article>
  );
}

function Info({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div>
      <p className="label-caps text-muted">{label}</p>
      <p className="mt-1 max-h-24 overflow-y-auto text-ink-secondary">{text(value)}</p>
    </div>
  );
}
