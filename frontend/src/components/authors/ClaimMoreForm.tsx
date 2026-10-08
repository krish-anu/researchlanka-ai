"use client";

import { useActionState, useEffect, useState } from "react";

import { requestAuthorClaimsAction } from "@/app/actions/authors";
import { SubmitButton } from "@/components/admin/ActionResult";
import { ClaimPicker, type ClaimDraft } from "@/components/authors/ClaimPicker";
import { FormMessage } from "@/components/authors/FormFields";
import { AUTHOR_FORM_IDLE } from "@/services/forms/state";

/** Claim publications after approval; each new claim waits for an administrator. */
export function ClaimMoreForm({
  names,
  claimedKeys,
  max,
  mySlug,
}: {
  names: string[];
  claimedKeys: string[];
  max: number;
  mySlug: string;
}) {
  const [state, formAction] = useActionState(requestAuthorClaimsAction, AUTHOR_FORM_IDLE);
  const [claims, setClaims] = useState<ClaimDraft[]>([]);
  const [spellings, setSpellings] = useState<string[]>([]);

  // Once sent, the claims show in the list above; clear the picker so they
  // are not sent twice.
  useEffect(() => {
    if (state.status === "ok") {
      setClaims([]);
      setSpellings([]);
    }
  }, [state]);

  return (
    <form action={formAction} className="flex flex-col gap-3">
      <input type="hidden" name="name_variants" value={JSON.stringify(spellings)} />
      <input
        type="hidden"
        name="claims"
        value={JSON.stringify(claims.map(({ publication_key, name_as_listed }) => ({ publication_key, name_as_listed })))}
      />
      <ClaimPicker
        value={claims}
        onChange={setClaims}
        names={names}
        max={max}
        excludeKeys={claimedKeys}
        mySlug={mySlug}
        onSpellingAdded={(spelling) =>
          setSpellings((current) => (current.includes(spelling) ? current : [...current, spelling]))
        }
        selectedLabel="To send for review"
        emptyHint="Search above and add the publications that are yours."
        invalid={state.status === "error" && state.field === "claims"}
      />
      <div className="flex flex-wrap items-center gap-3">
        <SubmitButton
          label="Send for review"
          pendingLabel="Sending…"
          tone="primary"
          disabled={claims.length === 0}
        />
        <FormMessage status={state.status} message={state.message} />
      </div>
    </form>
  );
}
