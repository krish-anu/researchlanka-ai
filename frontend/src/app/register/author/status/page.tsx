import Link from "next/link";
import { redirect } from "next/navigation";

import { signOut } from "@/app/actions/auth";
import { StatusBadge } from "@/components/authors/StatusBadge";
import { Button } from "@/components/ui/Button";
import { ApiErrorPanel } from "@/components/ui/Feedback";
import { requireAccount } from "@/services/auth/server";
import { getAuthorWorkspace } from "@/services/authors";
import { asApiFailure } from "@/services/backend";
import { formatDate } from "@/services/format";
import { publicationHref } from "@/services/links";
import { CLAIM_STATUS_LABEL, PROFILE_STATUS_LABEL } from "@/types/authors";

export const metadata = { title: "Your author application" };

/**
 * Where an author sign-up lands, and the only page its account can use until
 * an administrator decides. There is no email in this round, so this page is
 * how an applicant hears the outcome.
 */
export default async function AuthorApplicationStatusPage() {
  const { user, status: accountStatus } = await requireAccount("/register/author/status");
  const workspace = await getAuthorWorkspace(user);
  if (!workspace.ok) {
    return <ApiErrorPanel error={asApiFailure(workspace)} what="your author application" />;
  }
  const { profile, claims } = workspace.data;
  if (accountStatus === "active" && profile?.status === "approved") redirect("/account/author");

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <header>
        <p className="page-eyebrow">Author profiles</p>
        <h1 className="mt-1 font-display text-h1 text-ink">Your author application</h1>
        <p className="data-mono mt-1 text-muted">{user.email}</p>
      </header>

      {!profile ? (
        <section className="panel border-l-[3px] border-l-serious p-5">
          <h2 className="font-display text-h3 text-ink">We have no application from this account</h2>
          <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
            Your account exists, but the application did not reach the server. Send it again.
          </p>
          <Button href="/register/author" variant="primary" className="mt-4">
            Complete your application
          </Button>
        </section>
      ) : (
        <section className="panel p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="font-display text-h3 text-ink">{profile.display_name}</h2>
            <StatusBadge status={profile.status} label={PROFILE_STATUS_LABEL[profile.status]} />
          </div>
          <p className="mt-1 text-body-sm text-muted">
            {profile.institution}
            {profile.department ? ` · ${profile.department}` : ""} · submitted {formatDate(profile.submitted_at)}
          </p>

          {profile.status === "pending" ? (
            <p className="mt-4 max-w-prose text-body-sm text-ink-secondary">
              An administrator is reviewing your application. There is nothing more you need to do —
              sign in again any time to see the outcome here.
            </p>
          ) : null}

          {profile.status === "changes_requested" || profile.status === "rejected" ? (
            <div className="mt-4 rounded border border-l-[3px] border-rule border-l-warning bg-surface p-3">
              <p className="label-caps text-muted">
                {profile.status === "rejected" ? "Reason" : "What the reviewer asked for"}
              </p>
              <p className="mt-1 whitespace-pre-line text-body-sm text-ink">{profile.decision_reason}</p>
              <p className="mt-2 text-body-sm text-muted">Decided {formatDate(profile.decided_at)}</p>
            </div>
          ) : null}

          {profile.status === "changes_requested" ? (
            <Button href="/register/author" variant="primary" className="mt-4">
              Update your application
            </Button>
          ) : null}

          {profile.status === "rejected" ? (
            <p className="mt-4 max-w-prose text-body-sm text-ink-secondary">
              If you think this is a mistake, contact a platform administrator.
              {accountStatus === "active"
                ? " Your account keeps working as before."
                : " This account cannot be used for anything else."}
            </p>
          ) : null}

          {profile.status === "approved" ? (
            <p className="mt-4 text-body-sm text-ink-secondary">
              Approved. <Link href="/account/author" className="text-primary underline">Open your author tools</Link>.
            </p>
          ) : null}

          <h3 className="label-caps mt-6 text-muted">Publications you claimed ({claims.length})</h3>
          {claims.length === 0 ? (
            <p className="mt-2 text-body-sm text-muted">None. You can add them after approval.</p>
          ) : (
            <ul className="mt-2 flex flex-col divide-y divide-rule rounded border border-rule">
              {claims.map((claim) => (
                <li key={claim.claim_id} className="flex flex-wrap items-start justify-between gap-2 p-3">
                  <div className="min-w-0">
                    <Link href={publicationHref(claim.publication_key)} className="text-body-sm text-ink hover:text-primary hover:underline">
                      {claim.publication.title ?? claim.publication_key}
                    </Link>
                    <p className="text-body-sm text-muted">
                      Listed as {claim.name_as_listed}
                      {claim.publication.publication_year ? ` · ${claim.publication.publication_year}` : ""}
                    </p>
                    {claim.status === "rejected" && claim.decision_reason ? (
                      <p className="text-body-sm text-serious">{claim.decision_reason}</p>
                    ) : null}
                  </div>
                  <StatusBadge status={claim.status} label={CLAIM_STATUS_LABEL[claim.status]} />
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {accountStatus !== "active" ? (
        <form action={signOut}>
          <Button type="submit" variant="secondary">
            Sign out
          </Button>
        </form>
      ) : (
        <Link href="/account" className="text-body-sm text-primary underline">
          Back to your workspace
        </Link>
      )}
    </div>
  );
}
