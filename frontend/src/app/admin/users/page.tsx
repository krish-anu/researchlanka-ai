import { UserRow, type AdminUserView } from "@/components/admin/UserRow";
import { SectionHeading } from "@/components/ui/Feedback";
import { StatTile, StatTileGrid } from "@/components/ui/StatTile";
import { requireCapability } from "@/services/auth/server";
import { listUsers } from "@/services/auth/store";
import { formatNumber } from "@/services/format";
import { accountStatus } from "@/types/auth";

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
    status: accountStatus(user),
    created_at: user.created_at,
    last_login_at: user.last_login_at,
  }));

  const admins = view.filter((user) => user.role === "admin").length;
  const reviewers = view.filter((user) => user.role === "reviewer").length;
  const suspended = view.filter((user) => user.disabled).length;
  const awaiting = view.filter((user) => user.status === "pending").length;

  return (
    <div className="flex flex-col gap-6">
      <SectionHeading
        level={1}
        title="Accounts"
        description="Every account on the platform. Role changes and suspensions apply on that person's next guarded request."
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
          label="Awaiting approval"
          value={formatNumber(awaiting)}
          caption="author sign-ups not yet active"
        />
        <StatTile
          label="Signed-in users"
          value={formatNumber(view.length - admins - reviewers)}
          caption="standard accounts"
        />
      </StatTileGrid>

      <p className="text-body-sm text-muted">
        Role changes and suspensions apply on that person's next guarded request.
      </p>

      <div className="flex flex-col gap-4">
        {view.map((user) => (
          <UserRow key={user.id} user={user} isSelf={user.id === actor.id} />
        ))}
      </div>
    </div>
  );
}
