import Link from "next/link";

import { ClaimMoreForm } from "@/components/authors/ClaimMoreForm";
import { ProfileEditor } from "@/components/authors/ProfileEditor";
import { RemoveClaimButton } from "@/components/authors/RemoveClaimButton";
import { StatusBadge } from "@/components/authors/StatusBadge";
import { WithdrawButton } from "@/components/authors/WithdrawButton";
import { Button } from "@/components/ui/Button";
import { ApiErrorPanel, EmptyState, SectionHeading } from "@/components/ui/Feedback";
import { requireCapability } from "@/services/auth/server";
import { getAuthorWorkspace } from "@/services/authors";
import { asApiFailure } from "@/services/backend";
import { formatDate } from "@/services/format";
import { authorEditHref, authorProfileHref, publicationHref } from "@/services/links";
import {
  CLAIM_STATUS_LABEL,
  CONTRIBUTION_STATUS_LABEL,
  CONTRIBUTION_TYPE_LABEL,
  PROFILE_STATUS_LABEL,
  type Contribution,
  type NewPublicationProposal,
  type PublicationClaim,
} from "@/types/authors";

export const metadata = { title: "Author profile" };

interface PageProps {
  searchParams: Promise<{ sent?: string }>;
}

const SENT_NOTICE: Record<string, string> = {
  edit: "Your correction was sent. It shows on the public record once an administrator approves it.",
  publication:
    "Your publication was sent. An administrator checks that it is AI research and Sri Lanka-led before adding it.",
};

function contributionTitle(contribution: Contribution, claims: PublicationClaim[]): string {
  if (contribution.contribution_type === "new_publication") {
    return (contribution.proposed as NewPublicationProposal).title;
  }
  const claim = claims.find((item) => item.publication_key === contribution.publication_key);
  return claim?.publication.title ?? contribution.publication_key ?? "Publication";
}

export default async function AuthorWorkspacePage({ searchParams }: PageProps) {
  const user = await requireCapability("author.contribute", "/account/author");
  const { sent } = await searchParams;
  const result = await getAuthorWorkspace(user);
  if (!result.ok) {
    return <ApiErrorPanel error={asApiFailure(result)} what="your author profile" />;
  }
  const { profile, claims, contributions, limits } = result.data;

  if (!profile) {
    return (
      <section className="panel p-5">
        <h1 className="font-display text-h2 text-ink">Author profile</h1>
        <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
          If your publications are in this dataset, apply for a verified author profile. Once an
          administrator approves it you can write your own bio and links, suggest corrections to your
          publications and add papers the dataset is missing.
        </p>
        <Button href="/register/author" variant="primary" className="mt-4">
          Apply for an author profile
        </Button>
      </section>
    );
  }

  if (profile.status !== "approved") {
    return (
      <section className="panel p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="font-display text-h2 text-ink">Author profile</h1>
          <StatusBadge status={profile.status} label={PROFILE_STATUS_LABEL[profile.status]} />
        </div>
        <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
          {profile.status === "pending"
            ? "Your application is waiting for an administrator."
            : profile.status === "changes_requested"
              ? "An administrator asked you to update your application."
              : "Your application was not approved."}
        </p>
        <Button href="/register/author/status" variant="secondary" className="mt-4">
          See your application
        </Button>
      </section>
    );
  }

  const approved = claims.filter((claim) => claim.status === "approved");
  const waiting = claims.filter((claim) => claim.status !== "approved");
  const pendingEdits = new Set(
    contributions
      .filter((item) => item.status === "pending" && item.contribution_type === "publication_edit")
      .map((item) => item.publication_key),
  );
  const pendingCount = contributions.filter((item) => item.status === "pending").length;

  return (
    <div className="flex flex-col gap-6">
      {sent && SENT_NOTICE[sent] ? (
        <p role="status" className="rounded border border-l-[3px] border-rule border-l-good bg-surface px-3 py-2 text-body-sm text-success-text">
          {SENT_NOTICE[sent]}
        </p>
      ) : null}

      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-h1 text-ink">{profile.display_name}</h1>
          <p className="mt-1 text-body-sm text-muted">
            Verified author profile · approved {formatDate(profile.decided_at)}
          </p>
        </div>
        <Button href={authorProfileHref(profile.slug)} variant="secondary">
          View public profile
        </Button>
      </div>

      <section className="panel p-5">
        <SectionHeading title="Profile" description="Changes here are live on your public profile as soon as you save." />
        <ProfileEditor profile={profile} />
      </section>

      <section className="panel p-5">
        <SectionHeading
          title="Your publications"
          description="Suggest a correction to any of these. An administrator reviews it before it changes the public record."
        />
        {approved.length === 0 ? (
          <EmptyState bare title="No approved publications yet" description="Claim yours below, or add one the dataset is missing." />
        ) : (
          <ul className="flex flex-col divide-y divide-rule rounded border border-rule">
            {approved.map((claim) => (
              <li key={claim.claim_id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="min-w-0">
                  <Link href={publicationHref(claim.publication_key)} className="text-body-sm text-ink hover:text-primary hover:underline">
                    {claim.publication.title ?? claim.publication_key}
                  </Link>
                  <p className="text-body-sm text-muted">
                    {claim.publication.publication_year ?? "Year unknown"} · listed as {claim.name_as_listed}
                    {claim.publication.is_public ? "" : " · not currently public"}
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {pendingEdits.has(claim.publication_key) ? (
                    <span className="label-caps text-muted">Correction waiting for review</span>
                  ) : claim.publication.is_public ? (
                    <Button href={authorEditHref(claim.publication_key)} variant="secondary">
                      Suggest a correction
                    </Button>
                  ) : null}
                  <RemoveClaimButton claimId={claim.claim_id} />
                </div>
              </li>
            ))}
          </ul>
        )}

        {waiting.length > 0 ? (
          <>
            <h3 className="label-caps mt-5 text-muted">Claims waiting or declined</h3>
            <ul className="mt-2 flex flex-col divide-y divide-rule rounded border border-rule">
              {waiting.map((claim) => (
                <li key={claim.claim_id} className="flex flex-wrap items-start justify-between gap-2 p-3">
                  <div className="min-w-0">
                    <p className="text-body-sm text-ink">{claim.publication.title ?? claim.publication_key}</p>
                    <p className="text-body-sm text-muted">Listed as {claim.name_as_listed}</p>
                    {claim.status === "rejected" && claim.decision_reason ? (
                      <p className="text-body-sm text-serious">{claim.decision_reason}</p>
                    ) : null}
                  </div>
                  <StatusBadge status={claim.status} label={CLAIM_STATUS_LABEL[claim.status]} />
                </li>
              ))}
            </ul>
          </>
        ) : null}
      </section>

      <section className="panel p-5">
        <SectionHeading
          title="Claim more publications"
          description="Find papers already in the dataset that are yours, under every spelling of your name. Each claim is checked by an administrator."
        />
        <ClaimMoreForm
          names={[profile.display_name, ...profile.name_variants]}
          claimedKeys={claims.filter((claim) => claim.status !== "rejected").map((claim) => claim.publication_key)}
          max={limits.max_claims_per_request}
          mySlug={profile.slug}
        />
      </section>

      <section className="panel p-5">
        <SectionHeading
          title="Add a missing publication"
          description="For AI research you led from Sri Lanka that the dataset does not have yet. It is run through the same AI relevance check as harvested records."
          action={
            pendingCount >= limits.max_pending_contributions ? undefined : (
              <Button href="/account/author/new" variant="primary">
                Add a publication
              </Button>
            )
          }
        />
        {pendingCount >= limits.max_pending_contributions ? (
          <p className="text-body-sm text-muted">
            You have {pendingCount} submissions waiting for review. Add more once some are decided.
          </p>
        ) : null}
      </section>

      <section className="panel p-5">
        <SectionHeading title="Your submissions" description="Corrections and new publications you sent, newest first." />
        {contributions.length === 0 ? (
          <EmptyState bare title="Nothing sent yet" />
        ) : (
          <ul className="flex flex-col divide-y divide-rule rounded border border-rule">
            {contributions.map((contribution) => (
              <li key={contribution.contribution_id} className="flex flex-col gap-2 p-3 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="label-caps text-muted">{CONTRIBUTION_TYPE_LABEL[contribution.contribution_type]}</p>
                  <p className="text-body-sm text-ink">{contributionTitle(contribution, claims)}</p>
                  <p className="text-body-sm text-muted">
                    Sent {formatDate(contribution.created_at)}
                    {contribution.contribution_type === "publication_edit"
                      ? ` · ${Object.keys(contribution.proposed).join(", ").replace(/_/g, " ")}`
                      : ""}
                  </p>
                  {contribution.decision_reason ? (
                    <p className="mt-1 text-body-sm text-ink-secondary">
                      <span className="text-muted">Reviewer: </span>
                      {contribution.decision_reason}
                    </p>
                  ) : null}
                  {contribution.status === "approved" && contribution.publication_key ? (
                    <Link href={publicationHref(contribution.publication_key)} className="text-body-sm text-primary underline">
                      View the public record
                    </Link>
                  ) : null}
                </div>
                <div className="flex shrink-0 flex-col items-start gap-2 sm:items-end">
                  <StatusBadge status={contribution.status} label={CONTRIBUTION_STATUS_LABEL[contribution.status]} />
                  {contribution.status === "pending" ? <WithdrawButton contributionId={contribution.contribution_id} /> : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
