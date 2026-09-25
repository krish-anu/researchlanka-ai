import { AdminNav } from "@/components/admin/AdminNav";
import { RoleBadge } from "@/components/auth/RoleBadge";
import { cookies } from "next/headers";

import { readSessionToken, SESSION_COOKIE } from "@/services/auth/session";

export const metadata = {
  title: {
    default: "Administration",
    template: "%s · Administration · ResearchLanka",
  },
};

/**
 * Shell for the console.
 *
 * Middleware already rejects unsigned and non-admin cookies before this route
 * renders. Keep this layout free of deployment data reads so a broken JSON
 * store or missing artifact cannot collapse the whole admin shell; server
 * actions still re-check capabilities independently.
 */
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const store = await cookies();
  const user = await readSessionToken(store.get(SESSION_COOKIE)?.value);

  return (
    <div className="flex flex-col gap-6">
      <header className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h1 className="font-display text-h1 text-ink">
            System administration
          </h1>
          <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
            Ingestion health, quality control and curation queues. Public
            figures are computed by the pipeline — nothing here edits a
            published record directly.
          </p>
        </div>
        <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
          <RoleBadge role={user?.role ?? "admin"} />
          <span className="text-body-sm text-muted">
            {user?.email ?? "Administrator session"}
          </span>
        </div>
      </header>

      <AdminNav badges={{ flags: 0, review: 0, aiReview: 0 }} role={user?.role ?? "admin"} />

      {children}
    </div>
  );
}
