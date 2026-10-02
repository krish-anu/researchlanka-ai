import { AdminNav } from "@/components/admin/AdminNav";
import { RoleBadge } from "@/components/auth/RoleBadge";

import { getViewer } from "@/services/auth/server";

export const metadata = {
  title: {
    default: "Administration",
    template: "%s · Administration · ResearchLanka",
  },
};

/**
 * Shell for the console.
 *
 * Middleware only checks that a session exists; each page and action checks
 * capabilities against the live user store so role changes apply immediately.
 */
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const viewer = await getViewer();
  const user = viewer.user;

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
          <RoleBadge role={viewer.role} />
          <span className="text-body-sm text-muted">
            {user?.email ?? "Administrator session"}
          </span>
        </div>
      </header>

      <AdminNav badges={{ flags: 0, review: 0, aiReview: 0 }} role={viewer.role} />

      {children}
    </div>
  );
}
