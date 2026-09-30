import Link from "next/link";
import type { ReactNode } from "react";

import { assignPendingAIReviewsAction } from "@/app/actions/admin";
import { AIReviewCard } from "@/components/admin/AIReviewCard";
import { EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { Pagination } from "@/components/ui/Pagination";
import { requireCapability } from "@/services/auth/server";
import { listAIReviewCandidates } from "@/services/workspace/aiReview";
import { extractPage, type SearchParams } from "@/services/filters";
import { formatNumber } from "@/services/format";

export const metadata = { title: "AI review queue" };

const PAGE_SIZE = 20;

function stringParam(params: SearchParams, key: string): string | undefined {
  const value = params[key];
  return typeof value === "string" ? value : undefined;
}

export default async function AdminAIReviewPage({
  searchParams,
}: {
  searchParams: Promise<SearchParams>;
}) {
  const actor = await requireCapability("admin.resolution.decide", "/admin/ai-review");
  const params = await searchParams;
  const page = extractPage(params);
  const canManageReviewers = actor.role === "admin";
  const tab =
    canManageReviewers && stringParam(params, "tab") === "reviewers"
      ? "reviewers"
      : "queue";
  const view = stringParam(params, "view") === "all" ? "all" : stringParam(params, "view") === "completed" ? "completed" : "mine";
  const result = await listAIReviewCandidates({
    page,
    pageSize: PAGE_SIZE,
    view,
    status: stringParam(params, "status") ?? (view === "mine" ? "pending_review" : undefined),
    confidence: stringParam(params, "confidence"),
    reviewer: stringParam(params, "reviewer"),
    q: stringParam(params, "q"),
    actor,
  });
  const counts = result.stats.by_status;

  return (
    <div className="flex flex-col gap-8">
      <SectionHeading
        title="AI Review"
        description="PostgreSQL-backed review of Gemini AI relevance classifications, with durable reviewer assignment and Google Sheets sync."
      />

      <section className="grid gap-3 md:grid-cols-5">
        <Metric label="Pending" value={counts.pending_review ?? 0} />
        <Metric label="Auto accepted" value={counts.auto_accepted ?? 0} />
        <Metric label="Human accepted" value={counts.human_accepted ?? 0} />
        <Metric label="Human rejected" value={counts.human_rejected ?? 0} />
        <Metric label="Sync failures" value={result.stats.sync_failures} />
      </section>

      <nav className="flex flex-wrap gap-2 text-body-sm">
        <ViewLink href="/admin/ai-review" active={tab === "queue"}>Queue</ViewLink>
        {canManageReviewers ? (
          <ViewLink href="/admin/ai-review?tab=reviewers" active={tab === "reviewers"}>Reviewers</ViewLink>
        ) : null}
      </nav>

      {tab === "reviewers" ? (
        <ReviewersTab reviewers={result.stats.reviewers} pending={counts.pending_review ?? 0} />
      ) : (
        <>
          <section className="grid gap-3 md:grid-cols-3">
            {result.stats.reviewers.map((reviewer) => (
              <ReviewerSummary key={reviewer.email ?? "unassigned"} reviewer={reviewer} />
            ))}
          </section>

          <form className="panel grid gap-3 p-4 md:grid-cols-[1fr_auto_auto_auto]">
            <input
              name="q"
              defaultValue={stringParam(params, "q") ?? ""}
              placeholder="Search title, abstract, or DOI"
              className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink outline-none focus:border-primary"
            />
            <select
              name="view"
              defaultValue={view}
              className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink"
            >
              <option value="mine">My Pending Reviews</option>
              <option value="completed">Completed Reviews</option>
              <option value="all">All Reviews</option>
            </select>
            <select
              name="confidence"
              defaultValue={stringParam(params, "confidence") ?? ""}
              className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink"
            >
              <option value="">Any confidence</option>
              <option value="HIGH">HIGH</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="LOW">LOW</option>
              <option value="UNRECOGNIZED">Unrecognized</option>
            </select>
            <button className="rounded bg-ink px-4 py-2 text-body-sm font-semibold text-surface">
              Filter
            </button>
          </form>

          <nav className="flex flex-wrap gap-2 text-body-sm">
            <ViewLink href="/admin/ai-review" active={view === "mine"}>My Pending Reviews</ViewLink>
            <ViewLink href="/admin/ai-review?view=completed" active={view === "completed"}>Completed Reviews</ViewLink>
            <ViewLink href="/admin/ai-review?view=all" active={view === "all"}>All Reviews</ViewLink>
          </nav>

          {result.data.length === 0 ? (
            <EmptyState
              title="No review records found"
              description="Run the idempotent AI review backfill command after migrations, or adjust the current filters."
            />
          ) : (
            <div className="flex flex-col gap-4">
              {result.data.map((candidate) => (
                <AIReviewCard key={candidate.publication_key} candidate={candidate} />
              ))}
            </div>
          )}

          <Pagination
            pagination={result.pagination}
            basePath="/admin/ai-review"
            searchParams={params}
          />
        </>
      )}
    </div>
  );
}

type ReviewerStat = {
  email: string | null;
  name: string | null;
  pending: number;
  completed: number;
  total: number;
};

function ReviewersTab({
  reviewers,
  pending,
}: {
  reviewers: ReviewerStat[];
  pending: number;
}) {
  async function assignPendingFormAction() {
    "use server";
    await assignPendingAIReviewsAction();
  }

  const unassigned = reviewers.find((reviewer) => !reviewer.email);
  const assigned = reviewers.filter((reviewer) => reviewer.email);

  return (
    <section className="flex flex-col gap-4">
      <div className="panel flex flex-col gap-4 p-5 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="label-caps text-muted">Pending assignment</p>
          <h3 className="mt-1 font-display text-h3 text-ink">
            {formatNumber(unassigned?.pending ?? 0)} unassigned
          </h3>
          <p className="mt-1 text-body-sm text-ink-secondary">
            {formatNumber(pending)} pending records total across all reviewers.
          </p>
        </div>
        <form action={assignPendingFormAction}>
          <button className="rounded bg-primary px-4 py-2 text-body-sm font-semibold text-on-primary">
            Assign unassigned pending
          </button>
        </form>
      </div>

      <div className="grid gap-3 md:grid-cols-3">
        {unassigned ? <ReviewerSummary reviewer={unassigned} /> : null}
        {assigned.map((reviewer) => (
          <ReviewerSummary key={reviewer.email ?? "unassigned"} reviewer={reviewer} />
        ))}
      </div>
    </section>
  );
}

function ReviewerSummary({ reviewer }: { reviewer: ReviewerStat }) {
  const isUnassigned = !reviewer.email;
  return (
    <div className="panel p-4">
      <p className="label-caps text-muted">
        {isUnassigned ? "Unassigned" : reviewer.name || reviewer.email}
      </p>
      <p className="mt-1 font-display text-h3 text-ink">
        {formatNumber(reviewer.pending)} pending
      </p>
      <p className="text-body-sm text-ink-secondary">
        {formatNumber(reviewer.completed)} completed · {formatNumber(reviewer.total)} total
      </p>
      {reviewer.email ? (
        <Link
          href={`/admin/ai-review?view=all&status=pending_review&reviewer=${encodeURIComponent(reviewer.email)}`}
          className="mt-3 inline-block text-body-sm text-primary hover:underline"
        >
          View pending
        </Link>
      ) : null}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="panel p-4">
      <p className="label-caps text-muted">{label}</p>
      <p className="mt-1 font-display text-h2 text-ink">{formatNumber(value)}</p>
    </div>
  );
}

function ViewLink({
  href,
  active,
  children,
}: {
  href: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`rounded border px-3 py-2 ${active ? "border-ink bg-ink text-surface" : "border-rule bg-surface text-ink-secondary"}`}
    >
      {children}
    </Link>
  );
}
