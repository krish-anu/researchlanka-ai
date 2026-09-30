import { AdminNav } from "@/components/admin/AdminNav";
import { RoleBadge } from "@/components/auth/RoleBadge";
import { cookies } from "next/headers";

import { loadAdminNavBadges } from "@/services/admin/navBadges";
import { readSessionToken, SESSION_COOKIE } from "@/services/auth/session";

export const metadata = {
  title: {
    default: "Administration",
    template: "%s · Administration · ResearchLanka",
  },
};

/**
 * Console shell — denser than the public chrome so admin work reads as its
 * own mode. Middleware already rejects non-admins; pages own their headings.
 */
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const store = await cookies();
  const user = await readSessionToken(store.get(SESSION_COOKIE)?.value);
  const role = user?.role ?? "admin";
  const badges = (await loadAdminNavBadges(role)) ?? {
    flags: 0,
    review: 0,
    aiReview: 0,
  };

  return (
<<<<<<< HEAD
    <div className="admin-shell flex flex-col gap-5">
      <header className="admin-shell-strip">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="page-eyebrow">Administration</p>
            <p className="mt-1 max-w-prose text-body-sm text-ink-secondary">
              Ingestion health, quality control, and curation queues. Public
              figures come from the pipeline — nothing here edits a published
              record directly.
            </p>
          </div>
          <div className="flex shrink-0 flex-col items-start gap-1 sm:items-end">
            <RoleBadge role={role} />
            <span className="data-mono text-label text-muted">
              {user?.email ?? "Administrator session"}
            </span>
          </div>
        </div>
      </header>

      <div className="md:hidden">
        <AdminNav badges={badges} role={role} />
      </div>
=======
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
>>>>>>> origin/main

      {children}
    </div>
  );
}
