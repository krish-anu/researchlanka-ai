import Link from "next/link";

import { AuthorApplicationCard } from "@/components/admin/AuthorApplicationCard";
import { AuthorClaimCard } from "@/components/admin/AuthorClaimCard";
import { DecisionNotice } from "@/components/admin/DecisionNotice";
import { QueueFilter } from "@/components/admin/QueueFilter";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { requireCapability } from "@/services/auth/server";
import {
  getAuthorQueueSummary,
  listAuthorApplications,
  listAuthorClaimRequests,
} from "@/services/authors";
import { asApiFailure } from "@/services/backend";
import type { SessionUser } from "@/types/auth";

export const metadata = { title: "Author applications" };

interface PageProps {
  searchParams: Promise<{ tab?: string; status?: string; page?: string; decided?: string }>;
}

const STATUSES = [
  { value: "pending", label: "Waiting" },
  { value: "changes_requested", label: "Changes requested" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "all", label: "All" },
];

export default async function AdminAuthorsPage({ searchParams }: PageProps) {
  const actor = await requireCapability("admin.authors.manage", "/admin/authors");
  const query = await searchParams;
  const tab = query.tab === "claims" ? "claims" : "applications";
  const status = STATUSES.some((option) => option.value === query.status) ? String(query.status) : "pending";
  const page = Math.max(1, Number(query.page) || 1);

  const summary = await getAuthorQueueSummary();
  const counts = summary.ok ? summary.data : { applications: 0, claims: 0, contributions: 0 };

  return (
    <div className="flex flex-col gap-6">
      <SectionHeading
        level={1}
        title="Author applications"
        description="Researchers asking for a verified author profile, and approved authors claiming more publications. Email addresses are not verified yet, so weigh the ORCID and name evidence, and check with the institution when in doubt."
      />

      <DecisionNotice code={query.decided} />

      <QueueFilter
        label="Queue"
        current={tab}
        options={[
          { value: "applications", label: "Applications", count: counts.applications },
          { value: "claims", label: "Additional claims", count: counts.claims },
        ]}
        hrefFor={(value) => (value === "claims" ? "/admin/authors?tab=claims" : "/admin/authors")}
      />

      {tab === "applications" ? (
        <Applications actor={actor} status={status} page={page} />
      ) : (
        <Claims actor={actor} page={page} />
      )}
    </div>
  );
}

async function Applications({ actor, status, page }: { actor: SessionUser; status: string; page: number }) {
  const result = await listAuthorApplications(actor, { status, page });
  const hasMore = result.ok && (result.data.total ?? 0) > result.data.page * result.data.page_size;

  return (
    <section className="flex flex-col gap-4">
      <QueueFilter
        label="Application status"
        current={status}
        options={STATUSES}
        hrefFor={(value) => (value === "pending" ? "/admin/authors" : `/admin/authors?status=${value}`)}
      />
      {!result.ok ? (
        <ApiErrorPanel error={asApiFailure(result)} what="author applications" />
      ) : result.data.records.length === 0 ? (
        <EmptyState
          title={status === "pending" ? "No applications waiting" : "No applications here"}
          description="Researchers apply from the author sign-up page or from their account."
        />
      ) : (
        <>
          {result.data.records.map((application) => (
            <AuthorApplicationCard
              key={`${application.profile_id}-${application.record_version}`}
              application={application}
            />
          ))}
          {hasMore ? (
            <Link href={`/admin/authors?status=${status}&page=${page + 1}`} className="text-body-sm text-primary underline">
              Next page
            </Link>
          ) : null}
        </>
      )}
    </section>
  );
}

async function Claims({ actor, page }: { actor: SessionUser; page: number }) {
  const result = await listAuthorClaimRequests(actor, page);
  if (!result.ok) return <ApiErrorPanel error={asApiFailure(result)} what="publication claims" />;
  if (result.data.records.length === 0) {
    return (
      <EmptyState
        title="No claims waiting"
        description="Approved authors add publications to their profile from their author page."
      />
    );
  }
  return (
    <section className="flex flex-col gap-4">
      {result.data.records.map((claim) => (
        <AuthorClaimCard key={claim.claim_id} claim={claim} />
      ))}
    </section>
  );
}
