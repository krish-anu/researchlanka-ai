import { AdminNav } from "@/components/admin/AdminNav";
import { RoleBadge } from "@/components/auth/RoleBadge";
import { requireCapability } from "@/services/auth/server";
import { countPendingCandidates } from "@/services/workspace/resolution";
import { countOpenFlags } from "@/services/workspace/store";

export const metadata = {
  title: {
    default: "Administration",
    template: "%s · Administration · ResearchLanka",
  },
};

/**
 * Authoritative gate for the console.
 *
 * Everything below this layout assumes an administrator, so the check lives
 * here rather than being repeated in each page — though the server actions
 * re-check independently, since they are reachable without rendering a page.
 */
export default async function AdminLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const user = await requireCapability("admin.access", "/admin");

  const [flags, review] = await Promise.all([
    countOpenFlags(),
    countPendingCandidates(),
  ]);

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
          <RoleBadge role="admin" />
          <span className="text-body-sm text-muted">{user.email}</span>
        </div>
      </header>

      <AdminNav badges={{ flags, review }} />

      {children}
    </div>
  );
}
