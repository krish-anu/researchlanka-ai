"use client";

import { useEffect, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import {
  IncrementalUpdateDiagram,
  type IncrementalRunSnapshot,
} from "@/components/admin/IncrementalUpdateDiagram";
import { formatDate, formatNumber } from "@/services/format";

interface StatusResponse {
  data?: IncrementalRunSnapshot;
  error?: { message?: string };
}

export function ManualAIUpdatePanel({
  initialRun,
}: {
  initialRun: IncrementalRunSnapshot;
}) {
  const [run, setRun] = useState(initialRun);
  const [fromDate, setFromDate] = useState(initialRun.fromDate ?? "");
  const [toDate, setToDate] = useState(initialRun.toDate ?? "");
  const [threshold, setThreshold] = useState(
    String(initialRun.reviewThreshold ?? "0.85"),
  );
  const [message, setMessage] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const running = run.status === "running" || run.status === "queued";

  async function refreshStatus() {
    const response = await fetch("/api/admin/incremental/status", {
      cache: "no-store",
    });
    const payload = (await response.json()) as StatusResponse;
    if (!response.ok) {
      setMessage(payload.error?.message ?? "Could not refresh update status.");
      return;
    }
    if (payload.data) setRun(payload.data);
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    if (fromDate && toDate && fromDate > toDate) {
      setMessage("From date has to be on or before the to date.");
      return;
    }
    const thresholdValue = Number(threshold);
    if (!Number.isFinite(thresholdValue) || thresholdValue < 0 || thresholdValue > 1) {
      setMessage("Review threshold has to be a number from 0 to 1.");
      return;
    }
    setSubmitting(true);
    const response = await fetch("/api/admin/incremental/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        fromDate: fromDate || undefined,
        toDate: toDate || undefined,
        reviewThreshold: threshold,
      }),
    });
    const payload = (await response.json()) as StatusResponse;
    setSubmitting(false);
    if (!response.ok) {
      setMessage(payload.error?.message ?? "Could not start the AI update.");
      return;
    }
    setMessage("Incremental AI update started. The diagram will refresh while it runs.");
    await refreshStatus();
  }

  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      void refreshStatus();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [running]);

  return (
    <div className="grid items-start gap-3 xl:grid-cols-[22rem_minmax(0,1fr)]">
      <form className="panel p-3" onSubmit={submit}>
        <h3 className="font-display text-h3 text-ink">Manual AI update</h3>
        <p className="mt-1 text-body-sm text-ink-secondary">
          The date window and threshold are sent with the run. Records below the threshold stay in review and are not loaded as AI.
        </p>
        <div className="mt-5 grid gap-4">
          <label className="grid gap-2">
            <span className="label-caps text-muted">From date</span>
            <input
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
              className="min-h-11 rounded border border-rule bg-surface px-3 text-body-sm text-ink"
            />
          </label>
          <label className="grid gap-2">
            <span className="label-caps text-muted">To date</span>
            <input
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className="min-h-11 rounded border border-rule bg-surface px-3 text-body-sm text-ink"
            />
          </label>
          <label className="grid gap-2">
            <span className="label-caps text-muted">Review threshold</span>
            <input
              type="number"
              min="0"
              max="1"
              step="0.01"
              value={threshold}
              onChange={(event) => setThreshold(event.target.value)}
              className="min-h-11 rounded border border-rule bg-surface px-3 text-body-sm text-ink"
            />
          </label>
          <div className="flex flex-wrap gap-2 pt-2">
            <Button
              type="submit"
              variant="primary"
              disabled={submitting || running}
              loading={submitting}
            >
              {running && !submitting ? "Running..." : "Run AI update"}
            </Button>
            <Button
              type="button"
              variant="secondary"
              onClick={() => void refreshStatus()}
            >
              Refresh status
            </Button>
          </div>
          {message ? (
            <p className="text-body-sm text-ink-secondary">{message}</p>
          ) : null}
        </div>

        <dl className="mt-6 grid gap-3 border-t border-rule pt-4">
          <SummaryRow label="Status" value={run.status} />
          <SummaryRow label="Started" value={formatDate(run.startedAt ?? null)} />
          <SummaryRow label="Finished" value={formatDate(run.finishedAt ?? null)} />
          <SummaryRow label="Collected" value={formatNumber(run.collected ?? null)} />
          <SummaryRow label="Selected" value={formatNumber(run.selected ?? null)} />
          <SummaryRow label="New records" value={formatNumber(run.newRecords ?? null)} />
          <SummaryRow label="Updated records" value={formatNumber(run.updatedRecords ?? null)} />
          <SummaryRow label="Loaded / updated" value={formatNumber(run.loaded ?? null)} />
        </dl>
      </form>

      <IncrementalUpdateDiagram run={run} />
    </div>
  );
}

function SummaryRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule pb-2">
      <dt className="label-caps text-muted">{label}</dt>
      <dd className="text-right text-body-sm text-ink">{value}</dd>
    </div>
  );
}
