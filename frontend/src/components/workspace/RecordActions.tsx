"use client";

import Link from "next/link";
import { useActionState, useEffect, useState } from "react";
import { useFormStatus } from "react-dom";


import { submitPublicFeedback, toggleSave } from "@/app/actions/workspace";

import { Button } from "@/components/ui/Button";

import { IDLE, type ActionState } from "@/services/forms/state";
import { publicationHref } from "@/services/links";
import { FEEDBACK_REASON_LABEL } from "@/services/workspace/types";
import type { PublicationTrace } from "@/types/api";

const GUEST_PROMPT_DISMISSED_KEY = "rl-guest-save-flag-prompt";

function Pending({ label, pendingLabel }: { label: string; pendingLabel: string }) {
  const { pending } = useFormStatus();
  return (
    <Button
      type="submit"
      variant="secondary"
      size="sm"
      disabled={pending}
    >
      {pending ? pendingLabel : label}
    </Button>
  );
}

function Result({ state }: { state: ActionState }) {
  if (state.status === "idle") return null;
  return (
    <p
      role="status"
      className={`text-body-sm ${state.status === "ok" ? "text-success-text" : "text-serious"
        }`}
    >
      {state.message}
    </p>
  );
}

function SaveControl({
  publicationKey,
  title,
  initiallySaved,
}: {
  publicationKey: string;
  title: string;
  initiallySaved: boolean;
}) {
  const [state, formAction] = useActionState(toggleSave, IDLE);

  // The server's answer wins once it arrives; until then the button reflects
  // what the page was rendered with.
  const saved =
    state.status === "ok" ? state.message.startsWith("Saved") : initiallySaved;

  return (
    <form action={formAction} className="flex items-center gap-3">
      <input type="hidden" name="publication_key" value={publicationKey} />
      <input type="hidden" name="title" value={title} />
      <Pending
        label={saved ? "Remove from library" : "Save to library"}
        pendingLabel="Saving…"
      />
      <Result state={state} />
    </form>
  );
}

function FeedbackControl({
  publicationKey,
  title,
  trace,
}: {
  publicationKey: string;
  title: string;
  trace?: PublicationTrace;
}) {
  const [state, formAction] = useActionState(submitPublicFeedback, IDLE);
  const [open, setOpen] = useState(false);

  if (state.status === "ok") {
    return <Result state={state} />;
  }

  if (!open) {
    return (
      <Button
        type="button"
        variant="danger"
        size="sm"
        onClick={() => setOpen(true)}
      >

        Flag this record
      </Button>

    );
  }

  return (
    <form action={formAction} className="flex w-full flex-col gap-3">
      <input type="hidden" name="publication_key" value={publicationKey} />
      <input type="hidden" name="title" value={title} />
      <input type="hidden" name="page_url" value={publicationHref(publicationKey)} />
      <input type="hidden" name="dataset_version" value={trace?.dataset_version ?? ""} />
      <input
        type="hidden"
        name="classifier_version"
        value={trace?.classifier_version ?? ""}
      />
      <input
        type="hidden"
        name="classifier_decision"
        value={trace?.classifier_decision ?? ""}
      />
      <input
        type="hidden"
        name="classifier_probability"
        value={trace?.classifier_probability ?? ""}
      />

      <label className="flex flex-col gap-1.5">
        <span className="label-caps text-muted">What looks wrong?</span>
        <select
          name="report_type"
          required
          defaultValue="incorrect_ai_classification"
          className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink"
        >
          {Object.entries(FEEDBACK_REASON_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1.5">
        <span className="label-caps text-muted">Detail</span>
        <textarea
          name="detail"
          required
          minLength={10}
          maxLength={1000}
          rows={3}
          placeholder="What is wrong, and what should it be? Include a source if you have one."
          className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink placeholder:text-muted"
        />
      </label>

      <div className="flex flex-wrap items-center gap-2">

        <Pending label="Submit flag" pendingLabel="Submitting…" />
        <Button

          type="button"
          variant="ghost"
          size="sm"
          onClick={() => setOpen(false)}
        >
          Cancel
        </Button>
        <Result state={state} />
      </div>

      <p className="text-body-sm text-muted">
        Reports queue this record for curator review and can become hard
        training examples after a human correction. Nothing you submit edits
        the public record directly.
      </p>
    </form>
  );
}

/**
 * Save and public feedback controls.
 *
 * Visitors get the prompt rather than nothing at all: the difference between
 * the two roles is worth stating on the page where it bites, and hiding the
 * controls entirely would make the account look pointless.
 * Soft guest CTA for save/flag — shown once per session, then a quiet link.
 * Login page copy stays the full explanation; this only surfaces the offer
 * where the controls would appear.
 */
function GuestSaveFlagPrompt({ next }: { next: string }) {
  const [ready, setReady] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const loginHref = `/login?next=${encodeURIComponent(next)}`;

  useEffect(() => {
    try {
      setDismissed(sessionStorage.getItem(GUEST_PROMPT_DISMISSED_KEY) === "1");
    } catch {
      setDismissed(false);
    }
    setReady(true);
  }, []);

  // Avoid SSR/client mismatch until sessionStorage is read.
  if (!ready) return null;

  const dismiss = () => {
    try {
      sessionStorage.setItem(GUEST_PROMPT_DISMISSED_KEY, "1");
    } catch {
      /* private mode / blocked storage — still collapse for this view */
    }
    setDismissed(true);
  };

  if (dismissed) {
    return (
      <p className="text-body-sm text-muted">
        <Link href={loginHref} className="text-primary hover:underline">
          Sign in to save &amp; flag
        </Link>
      </p>
    );
  }

  return (
    <div
      className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-md border border-rule bg-wash px-3 py-2.5"
      role="note"
    >
      <p className="min-w-0 flex-1 text-body-sm text-ink-secondary">
        <strong className="font-medium text-ink">Sign in to save &amp; flag.</strong>{" "}
        Keep a library and report metadata that looks wrong.
      </p>
      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Button href={loginHref} variant="primary" size="sm">
          Sign in
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={dismiss}>
          Not now
        </Button>
      </div>
    </div>
  );
}

/**
 * Save and flag for signed-in readers, or a soft guest prompt near where
 * those controls live.
 */
export function RecordActions({
  publicationKey,
  title,
  signedIn,
  initiallySaved,
  trace,
}: {
  publicationKey: string;
  title: string;
  signedIn: boolean;
  initiallySaved: boolean;
  trace?: PublicationTrace;
}) {
  const next = publicationHref(publicationKey);

  if (!signedIn) {
    return (
      <div className="panel flex flex-col gap-3 p-4">
        <p className="text-body-sm text-ink-secondary">
          Reading this record needs no account. Signing in adds a saved library;
          public reports are open to everyone.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            href={`/login?next=${encodeURIComponent(next)}`}
            variant="primary"
            size="sm"
          >
            Sign in
          </Button>
          <Button
            href={`/register?next=${encodeURIComponent(next)}`}
            variant="secondary"
            size="sm"
          >
            Create an account
          </Button>
        </div>
        <div className="border-t border-rule pt-3">
          <FeedbackControl publicationKey={publicationKey} title={title} trace={trace} />
        </div>
      </div>
    );
    return <GuestSaveFlagPrompt next={publicationHref(publicationKey)} />;
  }

  return (
    <div className="panel flex flex-col gap-3 p-4">
      <SaveControl
        publicationKey={publicationKey}
        title={title}
        initiallySaved={initiallySaved}
      />
      <div className="border-t border-rule pt-3">
        <FeedbackControl publicationKey={publicationKey} title={title} trace={trace} />
      </div>
    </div>
  );
}
