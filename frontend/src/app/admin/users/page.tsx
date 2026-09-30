import { UserRow, type AdminUserView } from "@/components/admin/UserRow";
import { SectionHeading } from "@/components/ui/Feedback";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { requireCapability } from "@/services/auth/server";
import { listUsers } from "@/services/auth/store";
import { formatNumber } from "@/services/format";
import { ROLE_DESCRIPTION } from "@/types/auth";

export const metadata = { title: "Accounts" };

export default async function AdminUsersPage() {
  const actor = await requireCapability("admin.users.manage", "/admin/users");
  const users = await listUsers();

  const view: AdminUserView[] = users.map((user) => ({
    id: user.id,
    name: user.name,
    email: user.email,
    role: user.role,
    disabled: user.disabled,
    created_at: user.created_at,
    last_login_at: user.last_login_at,
  }));

  const admins = view.filter((user) => user.role === "admin").length;
  const reviewers = view.filter((user) => user.role === "reviewer").length;
  const suspended = view.filter((user) => user.disabled).length;

  return (
    <div className="flex flex-col gap-6">
      <SectionHeading
        title="Accounts and roles"
        description="Every account on the platform. Visitors are not listed — an unsigned visitor has no account, which is exactly what distinguishes the role."
      />

      <StatTileGrid>
        <StatTile
          label="Accounts"
          value={formatNumber(view.length)}
          caption="registered users"
        />
        <StatTile
          label="Administrators"
          value={formatNumber(admins)}
          caption="hold the admin role"
        />
        <StatTile
          label="Reviewers"
          value={formatNumber(reviewers)}
          caption="can review assigned AI records"
        />
        <StatTile
          label="Suspended"
          value={formatNumber(suspended)}
          caption="blocked from signing in"
        />
        <StatTile
          label="Signed-in users"
          value={formatNumber(view.length - admins - reviewers)}
          caption="standard accounts"
        />
      </StatTileGrid>

      <div className="panel p-4">
        <h2 className="label-caps text-muted">How roles behave</h2>
        <ul className="mt-2 flex flex-col gap-2 text-body-sm text-ink-secondary">
          <li>
            <strong className="text-ink">Visitor.</strong>{" "}
            {ROLE_DESCRIPTION.guest}
          </li>
          <li>
            <strong className="text-ink">Signed in.</strong>{" "}
            {ROLE_DESCRIPTION.user}
          </li>
          <li>
            <strong className="text-ink">Reviewer.</strong>{" "}
            {ROLE_DESCRIPTION.reviewer}
          </li>
          <li>
            <strong className="text-ink">Administrator.</strong>{" "}
            {ROLE_DESCRIPTION.admin}
          </li>
        </ul>
        <p className="mt-3 border-t border-rule pt-3 text-body-sm text-muted">
          Server-side route guards re-check the user store, so role changes and
          suspensions apply on that person's next guarded request.
        </p>
      </div>

      <div className="flex flex-col gap-4">
        {view.map((user) => (
          <UserRow key={user.id} user={user} isSelf={user.id === actor.id} />
        ))}
      </div>
    </div>
  );
}
