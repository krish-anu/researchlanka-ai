"use client";

import { useActionState } from "react";

import { withdrawContributionAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";

export function WithdrawButton({ contributionId }: { contributionId: string }) {
  const [state, formAction] = useActionState(withdrawContributionAction, AUTHOR_FORM_IDLE);
  return (
    <form action={formAction} className="flex flex-col items-end gap-1">
      <input type="hidden" name="contribution_id" value={contributionId} />
      <SubmitButton label="Withdraw" pendingLabel="Withdrawing…" />
      {state.status === "error" ? <p className="text-body-sm text-serious">{state.message}</p> : null}
    </form>
  );
}
