"use client";

import { useActionState } from "react";

import { decideResolution } from "@/app/actions/admin";
import { ActionResult, SubmitButton } from "@/components/admin/ActionResult";
import { SourceBadge } from "@/components/ui/Provenance";
import { IDLE } from "@/services/forms/state";
import type { ResolutionCandidate, ResolutionSide } from "@/services/workspace/types";

function Side({ side }: { side: ResolutionSide }) {
  return (
    <div className="flex min-w-0 flex-1 flex-col gap-2">
      <SourceBadge source={side.source} />
      <p className="font-display text-body-lg text-ink">{side.title}</p>
      <p className="data-mono truncate text-muted">
        {side.doi ? `DOI ${side.doi}` : "No DOI recorded"}
      </p>
      <p className="text-body-sm text-ink-secondary">
        {side.authors.join(", ")}
        {side.year ? ` · ${side.year}` : ""}
      </p>
    </div>
  );
}

/**
 * One duplicate candidate and its two-way decision.
 *
 * The pair is laid out side by side rather than stacked, because the reviewer's
 * whole job is a difference comparison and vertical stacking makes the reader
 * hold one record in memory while scrolling to the other. The confidence score
 * is stated as a number rather than a bar: at three decisions a minute, "0.71"
 * is faster to act on than a length.
 */
export function ResolutionCard({
  candidate,
}: {
  candidate: ResolutionCandidate;
}) {
  const [state, formAction] = useActionState(decideResolution, IDLE);
  const decided = candidate.status !== "pending";

  return (
    <article
      className={`panel p-5 ${decided ? "opacity-70" : "border-l-[3px] border-l-machine"}`}
    >
      <header className="mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-rule pb-3">
        <div className="flex items-center gap-2">
          <span className="label-caps text-machine">AI · match candidate</span>
          <span className="data-mono text-ink-secondary">
            confidence {candidate.score.toFixed(2)}
          </span>
        </div>
        {decided ? (
          <span className="label-caps text-muted">
            {candidate.status === "merged" ? "Merged" : "Kept separate"} by{" "}
            {candidate.decided_by}
          </span>
        ) : null}
      </header>

      <div className="flex flex-col gap-4 sm:flex-row sm:items-start">
        <Side side={candidate.left} />
        <div
          aria-hidden
          className="hidden self-center text-h2 text-muted sm:block"
        >
          ⇄
        </div>
        <Side side={candidate.right} />
      </div>

      {decided ? null : (
        <form
          action={formAction}
          className="mt-4 flex flex-wrap items-center gap-2 border-t border-rule pt-4"
        >
          <input type="hidden" name="candidate_id" value={candidate.id} />
          <SubmitButton
            name="decision"
            value="merged"
            label="Same work — merge"
            tone="primary"
          />
          <SubmitButton
            name="decision"
            value="rejected"
            label="Different works — keep both"
          />
          <p className="text-body-sm text-muted">
            Decisions are recorded now and applied on the next pipeline run.
          </p>
        </form>
      )}

      <ActionResult state={state} />
    </article>
  );
}
