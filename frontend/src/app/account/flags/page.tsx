import Link from "next/link";

import { EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { requireCapability } from "@/services/auth/server";
import { formatDate } from "@/services/format";
import { publicationHref } from "@/services/links";
import { listFlagsByUser } from "@/services/workspace/store";
import {
  FLAG_REASON_LABEL,
  FLAG_STATUS_LABEL,
  type FlagStatus,
} from "@/services/workspace/types";

export const metadata = { title: "Your flags" };

const STATUS_TONE: Record<FlagStatus, string> = {
  open: "border-l-warning",
  accepted: "border-l-good",
  rejected: "border-l-rule",
};

export default async function AccountFlagsPage() {
  const user = await requireCapability("record.flag", "/account/flags");
  const flags = await listFlagsByUser(user.id);

  return (
    <div>
      <SectionHeading
        title="Your flags"
        description="Records you reported as wrong. Flags do not change the data — the pipeline owns it — they queue a record for an administrator to check."
      />

      {flags.length === 0 ? (
        <EmptyState
          title="No flags raised"
          description="Use “Flag this record” on any publication where the metadata looks wrong."
          action={
            <Link
              href="/publications"
              className="mt-2 rounded bg-primary px-4 py-2 text-body-sm font-semibold text-on-primary hover:bg-primary-hover"
            >
              Search publications
            </Link>
          }
        />
      ) : (
        <ul className="flex flex-col gap-3">
          {flags.map((flag) => (
            <li
              key={flag.id}
              className={`panel border-l-[3px] p-4 ${STATUS_TONE[flag.status]}`}
            >
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <Link
                  href={publicationHref(flag.publication_key)}
                  className="font-display text-body-lg text-ink hover:text-primary hover:underline"
                >
                  {flag.title}
                </Link>
                <span className="label-caps text-muted">
                  {FLAG_STATUS_LABEL[flag.status]}
                </span>
              </div>
              <p className="mt-1 text-body-sm text-ink-secondary">
                {FLAG_REASON_LABEL[flag.reason]} · raised{" "}
                {formatDate(flag.created_at)}
              </p>
              <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
                {flag.detail}
              </p>
              {flag.status !== "open" ? (
                <p className="mt-2 border-t border-rule pt-2 text-body-sm text-muted">
                  {flag.resolution_note
                    ? `Reviewer: ${flag.resolution_note}`
                    : "Closed without a note."}
                </p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
