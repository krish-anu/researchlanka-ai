"use client";

import Link from "next/link";
import { useActionState } from "react";

import { triageFlag } from "@/app/actions/admin";
import { ActionResult, SubmitButton } from "@/components/admin/ActionResult";
import { IDLE } from "@/services/forms/state";
import { formatDate } from "@/services/format";
import { publicationHref } from "@/services/links";
import {
  FLAG_REASON_LABEL,
  FLAG_STATUS_LABEL,
  type RecordFlag,
} from "@/services/workspace/types";

const TONE: Record<RecordFlag["status"], string> = {
  open: "border-l-warning",
  accepted: "border-l-good",
  rejected: "border-l-rule",
};

/**
 * One reported record and its triage controls.
 *
 * Accepting a flag does not edit anything: metadata is pipeline-owned, so the
 * outcome is a recorded decision the next correction pass reads. The button
 * copy says so, because "Accept" on its own reads like an edit.
 */
export function FlagCard({ flag }: { flag: RecordFlag }) {
  const [state, formAction] = useActionState(triageFlag, IDLE);
  const open = flag.status === "open";

  return (
    <article className={`panel border-l-[3px] p-5 ${TONE[flag.status]}`}>
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <Link
          href={publicationHref(flag.publication_key)}
          className="font-display text-body-lg text-ink hover:text-primary hover:underline"
        >
          {flag.title}
        </Link>
        <span className="label-caps text-muted">
          {FLAG_STATUS_LABEL[flag.status]}
        </span>
      </header>

      <p className="data-mono mt-1 truncate text-muted">
        {flag.publication_key}
      </p>

      <p className="mt-3 text-body-sm font-medium text-ink">
        {FLAG_REASON_LABEL[flag.reason]}
      </p>
      <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
        {flag.detail}
      </p>

      <p className="mt-3 text-body-sm text-muted">
        Reported by {flag.reported_by.name} ({flag.reported_by.email}) on{" "}
        {formatDate(flag.created_at)}
      </p>

      {open ? (
        <form
          action={formAction}
          className="mt-4 flex flex-col gap-3 border-t border-rule pt-4"
        >
          <input type="hidden" name="flag_id" value={flag.id} />
          <label className="flex flex-col gap-1.5">
            <span className="label-caps text-muted">
              Note for the reporter (optional)
            </span>
            <input
              name="note"
              type="text"
              maxLength={300}
              placeholder="What you checked, and what happens next"
              className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink placeholder:text-muted"
            />
          </label>
          <div className="flex flex-wrap gap-2">
            <SubmitButton
              name="decision"
              value="accepted"
              label="Accept — queue for correction"
              tone="primary"
            />
            <SubmitButton
              name="decision"
              value="rejected"
              label="Reject — record is correct"
            />
          </div>
        </form>
      ) : (
        <p className="mt-3 border-t border-rule pt-3 text-body-sm text-muted">
          Closed by {flag.resolved_by} on {formatDate(flag.resolved_at)}
          {flag.resolution_note ? ` — ${flag.resolution_note}` : ""}
        </p>
      )}

      <ActionResult state={state} />
    </article>
  );
}
