import Link from "next/link";

import { RoleBadge } from "@/components/auth/RoleBadge";
import { getViewer } from "@/services/auth/server";
import { ROLE_DESCRIPTION } from "@/types/auth";

export const metadata = { title: "Not permitted" };

interface PageProps {
  searchParams: Promise<{ need?: string }>;
}

/**
 * Where a signed-in user lands when their role does not carry a capability.
 *
 * Deliberately not the sign-in form: they are already signed in, so the useful
 * information is which role they hold and who can change it.
 */
export default async function ForbiddenPage({ searchParams }: PageProps) {
  const { need } = await searchParams;
  const viewer = await getViewer();

  return (
    <div className="panel mx-auto max-w-2xl border-l-[3px] border-l-serious p-6 md:p-8">
      <h1 className="title-page text-ink">Not permitted</h1>
      <p className="mt-2 text-body-md text-ink-secondary">
        Your account does not have access to that area.
      </p>

      <div className="mt-5 border-t border-rule pt-4">
        <p className="label-caps text-muted">Your role</p>
        <div className="mt-2">
          <RoleBadge role={viewer.role} />
        </div>
        <p className="mt-2 max-w-prose text-body-sm text-ink-secondary">
          {ROLE_DESCRIPTION[viewer.role]}
        </p>
        {need ? (
          <p className="mt-3 text-body-sm text-muted">
            Required capability:{" "}
            <code className="data-mono rounded bg-sunk px-1 py-0.5">{need}</code>
          </p>
        ) : null}
      </div>

      <p className="mt-5 border-t border-rule pt-4 text-body-sm text-ink-secondary">
        Administrator access is granted from the user list by an existing
        administrator. Roles are read from your session, so a newly granted role
        takes effect the next time you sign in.
      </p>

      <div className="mt-5 flex flex-wrap gap-3">
        <Link
          href="/"
          className="rounded bg-primary px-4 py-2 text-body-sm font-semibold text-on-primary hover:bg-primary-hover"
        >
          Back to the dashboard
        </Link>
        <Link
          href="/account"
          className="rounded border border-rule px-4 py-2 text-body-sm text-ink-secondary hover:border-primary hover:text-primary"
        >
          Your account
        </Link>
      </div>
    </div>
  );
}
