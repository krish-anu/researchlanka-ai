"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import type { IncrementalJobStatus } from "@/services/admin/incremental";
import { formatDate, formatNumber } from "@/services/format";

export function PipelineRunPanel({
  status,
}: {
  status: IncrementalJobStatus;
}) {
  const [currentStatus, setCurrentStatus] = useState(status);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const router = useRouter();

  useEffect(() => {
    setCurrentStatus(status);
  }, [status]);

  useEffect(() => {
    if (currentStatus.status !== "running") return;
    const timer = window.setInterval(refreshStatus, 10_000);
    return () => window.clearInterval(timer);
  }, [currentStatus.status]);

  const running = currentStatus.status === "running";
  const result = currentStatus.result;

  async function refreshStatus() {
    const response = await fetch("/api/admin/incremental/status", {
      cache: "no-store",
    });
    if (!response.ok) {
      setError("Could not refresh the update status.");
      return;
    }
    setCurrentStatus(await response.json());
    router.refresh();
  }

  async function runUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    setMessage("");

    const form = new FormData(event.currentTarget);
    const response = await fetch("/api/admin/incremental/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        from_date: String(form.get("from_date") ?? ""),
        to_date: String(form.get("to_date") ?? ""),
        confidence_review_threshold: String(
          form.get("confidence_review_threshold") ?? "",
        ),
      }),
    });

    const payload = await response.json().catch(() => ({}));
    setSubmitting(false);
    if (!response.ok) {
      setError(
        typeof payload.error === "string"
          ? payload.error
          : "Could not start the incremental update.",
      );
      return;
    }

    setCurrentStatus(payload);
    setMessage("Incremental AI update started. Refresh this page to follow status.");
    router.refresh();
  }

  return (
    <div className="panel p-4">
      <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <form onSubmit={runUpdate} className="flex flex-col gap-3">
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
            <button
              type="submit"
              disabled={running || submitting}
              className="rounded border border-primary bg-primary px-3 py-1.5 text-body-sm font-medium text-on-primary transition-colors hover:bg-primary-hover disabled:opacity-60"
            >
              {submitting ? "Starting..." : running ? "Already running" : "Run AI update"}
            </button>
            <button
              type="button"
              onClick={() => void refreshStatus()}
              className="rounded border border-rule px-3 py-1.5 text-body-sm font-medium text-ink-secondary transition-colors hover:border-primary hover:text-primary"
            >
              Refresh status
            </button>
          </div>
          {message ? (
            <p role="status" className="mt-2 border-l-[3px] border-l-good pl-3 text-body-sm text-success-text">
              {message}
            </p>
          ) : null}
          {error ? (
            <p role="status" className="mt-2 border-l-[3px] border-l-serious pl-3 text-body-sm text-serious">
              {error}
            </p>
          ) : null}
        </form>

        <div className="border-t border-rule pt-4 lg:border-l lg:border-t-0 lg:pl-4 lg:pt-0">
          <dl className="grid gap-3 text-body-sm">
            <StatusRow label="Status" value={currentStatus.status} />
            <StatusRow label="Started" value={formatDate(currentStatus.started_at)} />
            <StatusRow label="Finished" value={formatDate(currentStatus.finished_at)} />
            <StatusRow label="Message" value={currentStatus.message} />
            {result ? (
              <>
                <StatusRow label="Collected" value={formatNumber(result.records_collected)} />
                <StatusRow label="Selected" value={formatNumber(result.records_selected_for_db)} />
                <StatusRow label="Loaded" value={formatNumber(result.records_loaded)} />
              </>
            ) : null}
            {currentStatus.log_path ? (
              <StatusRow label="Log" value={currentStatus.log_path} />
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
