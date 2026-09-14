"use client";

import { useActionState } from "react";

import { decideAIReviewAction } from "@/app/actions/admin";
import { ActionResult, SubmitButton } from "@/components/admin/ActionResult";
import { SourceBadge } from "@/components/ui/Provenance";
import { IDLE } from "@/services/forms/state";
import type { AIReviewCandidate } from "@/services/workspace/types";

function formatNumber(value: number | null): string {
  return value === null ? "n/a" : value.toFixed(3);
}

export function AIReviewCard({ candidate }: { candidate: AIReviewCandidate }) {
  const [state, formAction] = useActionState(decideAIReviewAction, IDLE);
  const decided = candidate.status === "decided";

  return (
    <article
      className={`panel p-5 ${decided ? "opacity-70" : "border-l-[3px] border-l-machine"}`}
    >
      <header className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-rule pb-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="label-caps text-machine">AI relevance review</span>
          <span className="data-mono text-ink-secondary">
            raw {candidate.raw_label} · confidence {formatNumber(candidate.confidence)}
          </span>
          <span className="data-mono text-muted">
            threshold {formatNumber(candidate.review_threshold)}
          </span>
        </div>
        {decided && candidate.decision ? (
          <span className="label-caps text-muted">
            {candidate.decision.decision} by {candidate.decision.decided_by}
          </span>
        ) : null}
      </header>

      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <SourceBadge source={candidate.source_dataset || "prediction"} />
          <span className="data-mono text-muted">
            row {candidate.source_row || "n/a"}
          </span>
          {candidate.publication_date ? (
            <span className="text-body-sm text-ink-secondary">
              {candidate.publication_date}
            </span>
          ) : null}
        </div>

        <h2 className="font-display text-h3 text-ink">
          {candidate.title || "Untitled publication"}
        </h2>

        <p className="data-mono break-all text-body-sm text-muted">
          {candidate.doi ? `DOI ${candidate.doi}` : "No DOI recorded"}
          {candidate.openalex_id ? ` · ${candidate.openalex_id}` : ""}
        </p>

        <dl className="grid gap-3 text-body-sm sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <dt className="label-caps text-muted">Topic</dt>
            <dd className="text-ink-secondary">{candidate.primary_topic || "n/a"}</dd>
          </div>
          <div>
            <dt className="label-caps text-muted">Subfield</dt>
            <dd className="text-ink-secondary">{candidate.primary_subfield || "n/a"}</dd>
          </div>
          <div>
            <dt className="label-caps text-muted">Field</dt>
            <dd className="text-ink-secondary">{candidate.primary_field || "n/a"}</dd>
          </div>
          <div>
            <dt className="label-caps text-muted">Domain</dt>
            <dd className="text-ink-secondary">{candidate.primary_domain || "n/a"}</dd>
          </div>
        </dl>

        <p className="max-h-32 overflow-y-auto border-t border-rule pt-3 text-body-sm text-ink-secondary">
          {candidate.text || "No model text available."}
        </p>
      </div>

      {decided ? (
        candidate.decision?.note ? (
          <p className="mt-4 border-t border-rule pt-3 text-body-sm text-ink-secondary">
            {candidate.decision.note}
          </p>
        ) : null
      ) : (
        <form
          action={formAction}
          className="mt-4 flex flex-col gap-3 border-t border-rule pt-4"
        >
          <input type="hidden" name="candidate_id" value={candidate.id} />
          <label className="flex flex-col gap-1 text-body-sm text-ink-secondary">
            Decision note
            <textarea
              name="note"
              rows={2}
              className="rounded border border-rule bg-surface px-3 py-2 text-ink outline-none focus:border-primary"
              placeholder="Optional reason for the final label"
            />
          </label>
          <div className="flex flex-wrap items-center gap-2">
            <SubmitButton
              name="decision"
              value="AI"
              label="Mark as AI"
              tone="primary"
            />
            <SubmitButton
              name="decision"
              value="NON_AI"
              label="Mark as Non-AI"
            />
            <p className="text-body-sm text-muted">
              Saves the decision and updates the resolved prediction file.
            </p>
          </div>
        </form>
      )}

      <ActionResult state={state} />
    </article>
  );
}
