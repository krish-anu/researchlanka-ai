"use client";

import { useActionState, useState } from "react";

import { removeClaimAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { Button } from "@/components/ui/Button";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";

/** "This is not mine": two steps, because the claim then needs re-approving to come back. */
export function RemoveClaimButton({ claimId }: { claimId: string }) {
  const [state, formAction] = useActionState(removeClaimAction, AUTHOR_FORM_IDLE);
  const [confirming, setConfirming] = useState(false);

  if (!confirming) {
    return (
      <Button type="button" variant="ghost" onClick={() => setConfirming(true)}>
        Not mine
      </Button>
    );
  }
  return (
    <form action={formAction} className="flex flex-wrap items-center gap-2">
      <input type="hidden" name="claim_id" value={claimId} />
      <span className="text-body-sm text-ink-secondary">Remove from your profile?</span>
      <SubmitButton label="Remove" pendingLabel="Removing…" tone="danger" />
      <Button type="button" variant="ghost" onClick={() => setConfirming(false)}>
        Keep
      </Button>
      {state.status === "error" ? <p className="w-full text-body-sm text-serious">{state.message}</p> : null}
    </form>
  );
}
