"use client";

import { useActionState } from "react";

import { changeUserRole, toggleUserAccess } from "@/app/actions/admin";
import { ActionResult, SubmitButton } from "@/components/admin/ActionResult";
import { RoleBadge } from "@/components/auth/RoleBadge";
import { IDLE } from "@/services/forms/state";
import { formatDate } from "@/services/format";
import type { AccountRole } from "@/types/auth";

export interface AdminUserView {
  id: string;
  name: string;
  email: string;
  role: AccountRole;
  disabled: boolean;
  created_at: string;
  last_login_at: string | null;
}

/**
 * One account, with its two levers: role and access.
 *
 * They are separate forms with separate result lines because they fail for
 * different reasons — "last administrator" blocks a demotion and a suspension
 * independently, and a shared message would leave the reader guessing which
 * button it answered.
 */
export function UserRow({
  user,
  isSelf,
}: {
  user: AdminUserView;
  isSelf: boolean;
}) {
  const [roleState, roleAction] = useActionState(changeUserRole, IDLE);
  const [accessState, accessAction] = useActionState(toggleUserAccess, IDLE);

  const nextRole: AccountRole = user.role === "admin" ? "user" : "admin";

  return (
    <article className="panel p-5">
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-display text-body-lg text-ink">
            {user.name}
            {isSelf ? (
              <span className="ml-2 text-body-sm text-muted">(you)</span>
            ) : null}
          </p>
          <p className="data-mono mt-1 truncate text-muted">{user.email}</p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <RoleBadge role={user.role} />
          {user.disabled ? (
            <span className="label-caps rounded border border-rule bg-surface px-2 py-1 text-serious">
              Suspended
            </span>
          ) : null}
        </div>
      </header>

      <dl className="mt-3 flex flex-wrap gap-x-8 gap-y-1 border-t border-rule pt-3 text-body-sm">
        <div className="flex gap-2">
          <dt className="text-muted">Created</dt>
          <dd className="text-ink-secondary">{formatDate(user.created_at)}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-muted">Last sign-in</dt>
          <dd className="text-ink-secondary">
            {user.last_login_at ? formatDate(user.last_login_at) : "Never"}
          </dd>
        </div>
      </dl>

      <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-rule pt-4">
        <form action={roleAction}>
          <input type="hidden" name="user_id" value={user.id} />
          <input type="hidden" name="role" value={nextRole} />
          <SubmitButton
            label={
              nextRole === "admin"
                ? "Grant administrator"
                : "Revoke administrator"
            }
            tone={nextRole === "admin" ? "primary" : "neutral"}
          />
        </form>

        <form action={accessAction}>
          <input type="hidden" name="user_id" value={user.id} />
          <input
            type="hidden"
            name="disable"
            value={user.disabled ? "false" : "true"}
          />
          <SubmitButton
            label={user.disabled ? "Reinstate" : "Suspend"}
            tone={user.disabled ? "neutral" : "danger"}
          />
        </form>
      </div>

      <ActionResult state={roleState} />
      <ActionResult state={accessState} />
    </article>
  );
}
