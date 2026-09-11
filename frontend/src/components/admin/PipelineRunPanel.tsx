"use client";

import { useActionState, useEffect } from "react";
import { useRouter } from "next/navigation";

import { runIncrementalUpdate } from "@/app/actions/admin";
import { ActionResult, SubmitButton } from "@/components/admin/ActionResult";
import { IDLE } from "@/services/forms/state";
import type { IncrementalJobStatus } from "@/services/admin/incremental";
import { formatDate, formatNumber } from "@/services/format";

export function PipelineRunPanel({
  status,
}: {
  status: IncrementalJobStatus;
}) {
  const [state, formAction] = useActionState(runIncrementalUpdate, IDLE);
  const router = useRouter();

  useEffect(() => {
    if (status.status !== "running") return;
    const timer = window.setInterval(() => router.refresh(), 10_000);
    return () => window.clearInterval(timer);
  }, [router, status.status]);

  const running = status.status === "running";
  const result = status.result;

  return (
    <div className="panel p-4">
      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <form action={formAction} className="flex flex-col gap-3">
          <div className="grid gap-3 md:grid-cols-3">
            <label className="flex flex-col gap-1 text-body-sm text-ink">
              <span className="label-caps text-muted">From date</span>
              <input
                name="from_date"
                type="date"
                className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink"
              />
            </label>
            <label className="flex flex-col gap-1 text-body-sm text-ink">
              <span className="label-caps text-muted">To date</span>
              <input
                name="to_date"
                type="date"
                className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink"
              />
            </label>
            <label className="flex flex-col gap-1 text-body-sm text-ink">
              <span className="label-caps text-muted">Review threshold</span>
              <input
                name="confidence_review_threshold"
                inputMode="decimal"
                className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink"
                placeholder="0.65"
              />
            </label>
          </div>
          <div className="flex flex-wrap items-center gap-3">
            <SubmitButton
              label={running ? "Already running" : "Run AI update"}
              pendingLabel="Starting..."
              tone="primary"
              disabled={running}
            />
            <button
              type="button"
              onClick={() => router.refresh()}
              className="rounded border border-rule px-3 py-1.5 text-body-sm font-medium text-ink-secondary transition-colors hover:border-primary hover:text-primary"
            >
              Refresh status
            </button>
          </div>
          <ActionResult state={state} />
        </form>

        <div className="border-t border-rule pt-4 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
          <dl className="grid gap-3 text-body-sm">
            <StatusRow label="Status" value={status.status} />
            <StatusRow label="Started" value={formatDate(status.started_at)} />
            <StatusRow label="Finished" value={formatDate(status.finished_at)} />
            <StatusRow label="Message" value={status.message} />
            {result ? (
              <>
                <StatusRow label="Collected" value={formatNumber(result.records_collected)} />
                <StatusRow label="Selected" value={formatNumber(result.records_selected_for_db)} />
                <StatusRow label="Loaded" value={formatNumber(result.records_loaded)} />
              </>
            ) : null}
            {status.log_path ? (
              <StatusRow label="Log" value={status.log_path} />
            ) : null}
          </dl>
        </div>
      </div>
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="grid gap-1 sm:grid-cols-[7rem_1fr]">
      <dt className="label-caps text-muted">{label}</dt>
      <dd className="min-w-0 break-words text-ink">{value || "-"}</dd>
    </div>
  );
}
