import Link from "next/link";

import { RoleBadge } from "@/components/auth/RoleBadge";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { ROLE_CAPABILITY_SUMMARY } from "@/services/auth/permissions";
import { requireCapability } from "@/services/auth/server";
import { findUserById } from "@/services/auth/store";
import { listFlagsByUser, listSavedItems } from "@/services/workspace/store";
import { formatDate, formatNumber } from "@/services/format";
import { ROLE_DESCRIPTION } from "@/types/auth";

export const metadata = { title: "Your account" };

export default async function AccountPage() {
  const session = await requireCapability("account.manage", "/account");

  const [record, saved, flags] = await Promise.all([
    findUserById(session.id),
    listSavedItems(session.id),
    listFlagsByUser(session.id),
  ]);

  const openFlags = flags.filter((flag) => flag.status === "open").length;

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="font-display text-h1 text-ink">{session.name}</h1>
        <p className="data-mono mt-1 text-muted">{session.email}</p>
        <div className="mt-3">
          <RoleBadge role={session.role} />
        </div>
      </div>

      <StatTileGrid>
        <StatTile
          label="Saved"
          value={formatNumber(saved.length)}
          caption="publications in your library"
        />
        <StatTile
          label="Flags raised"
          value={formatNumber(flags.length)}
          caption="records you reported"
        />
        <StatTile
          label="Awaiting review"
          value={formatNumber(openFlags)}
          caption="of your flags still open"
        />
        <StatTile
          label="Member since"
          value={formatDate(record?.created_at ?? null)}
          caption="account created"
        />
      </StatTileGrid>

      <section className="panel p-5">
        <h2 className="font-display text-h3 text-ink">
          What your role allows
        </h2>
        <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
          {ROLE_DESCRIPTION[session.role]}
        </p>
        <ul className="mt-3 flex flex-col gap-2 border-t border-rule pt-3 text-body-sm text-ink-secondary">
          {ROLE_CAPABILITY_SUMMARY[session.role].map((line) => (
            <li key={line} className="flex gap-2">
              <span aria-hidden className="text-muted">
                ·
              </span>
              {line}
            </li>
          ))}
        </ul>
        {session.role === "user" ? (
          <p className="mt-3 border-t border-rule pt-3 text-body-sm text-muted">
            Administrator access is granted by an existing administrator from
            the platform user list. It cannot be requested from this screen.
          </p>
        ) : (
          <Link
            href="/admin"
            className="mt-3 inline-block border-t border-rule pt-3 text-body-sm text-primary underline"
          >
            Open the administration console
          </Link>
        )}
      </section>

      <section className="panel p-5">
        <h2 className="font-display text-h3 text-ink">Session</h2>
        <dl className="mt-3 text-body-sm">
          <div className="flex justify-between border-b border-rule py-2">
            <dt className="text-muted">Last sign-in</dt>
            <dd className="text-ink-secondary">
              {formatDate(record?.last_login_at ?? null)}
            </dd>
          </div>
          <div className="flex justify-between py-2">
            <dt className="text-muted">Sign-in expires</dt>
            <dd className="text-ink-secondary">7 days after sign-in</dd>
          </div>
        </dl>
        <p className="mt-2 text-body-sm text-muted">
          Your role is carried in the session cookie, so a role change made by
          an administrator applies the next time you sign in.
        </p>
      </section>
    </div>
  );
}
