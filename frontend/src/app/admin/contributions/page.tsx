import Link from "next/link";

import { AuthorContributionCard } from "@/components/admin/AuthorContributionCard";
import { DecisionNotice } from "@/components/admin/DecisionNotice";
import { QueueFilter } from "@/components/admin/QueueFilter";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { getCategoryOptions } from "@/services/api";
import { requireCapability } from "@/services/auth/server";
import { listAuthorContributions } from "@/services/authors";
import { asApiFailure } from "@/services/backend";

export const metadata = { title: "Author contributions" };

interface PageProps {
  searchParams: Promise<{ type?: string; status?: string; page?: string; decided?: string }>;
}

const TYPES = [
  { value: "all", label: "Everything" },
  { value: "new_publication", label: "New publications" },
  { value: "publication_edit", label: "Corrections" },
];

const STATUSES = [
  { value: "pending", label: "Waiting" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
  { value: "all", label: "All" },
];

function queueHref(type: string, status: string, page = 1): string {
  const search = new URLSearchParams();
  if (type !== "all") search.set("type", type);
  if (status !== "pending") search.set("status", status);
  if (page > 1) search.set("page", String(page));
  const qs = search.toString();
  return qs ? `/admin/contributions?${qs}` : "/admin/contributions";
}

export default async function AdminContributionsPage({ searchParams }: PageProps) {
  const actor = await requireCapability("admin.authors.manage", "/admin/contributions");
  const query = await searchParams;
  const type = TYPES.some((option) => option.value === query.type) ? String(query.type) : "all";
  const status = STATUSES.some((option) => option.value === query.status) ? String(query.status) : "pending";
  const page = Math.max(1, Number(query.page) || 1);

  const [result, categories] = await Promise.all([
    listAuthorContributions(actor, {
      type: type === "all" ? undefined : type,
      status,
      page,
    }),
    getCategoryOptions(),
  ]);
  const categoryOptions = categories.ok ? categories.value.data.fields : [];
  const hasMore = result.ok && (result.data.total ?? 0) > result.data.page * result.data.page_size;

  return (
    <div className="flex flex-col gap-6">
      <SectionHeading
        level={1}
        title="Author contributions"
        description="Corrections and new publications sent by verified authors. Approved corrections show on the public record straight away and survive pipeline reloads. New publications enter the dataset only once you confirm they are AI research and Sri Lanka-led."
      />
      <DecisionNotice code={query.decided} />
      <div className="flex flex-col gap-2">
        <QueueFilter label="Contribution type" current={type} options={TYPES} hrefFor={(value) => queueHref(value, status)} />
        <QueueFilter label="Contribution status" current={status} options={STATUSES} hrefFor={(value) => queueHref(type, value)} />
      </div>
      {!result.ok ? (
        <ApiErrorPanel error={asApiFailure(result)} what="author contributions" />
      ) : result.data.records.length === 0 ? (
        <EmptyState title={status === "pending" ? "Nothing waiting for review" : "Nothing here"} />
      ) : (
        <section className="flex flex-col gap-4">
          {result.data.records.map((contribution) => (
            <AuthorContributionCard
              key={`${contribution.contribution_id}-${contribution.record_version}`}
              contribution={contribution}
              categories={categoryOptions}
            />
          ))}
          {hasMore ? (
            <Link href={queueHref(type, status, page + 1)} className="text-body-sm text-primary underline">
              Next page
            </Link>
          ) : null}
        </section>
      )}
    </div>
  );
}
