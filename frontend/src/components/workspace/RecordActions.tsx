"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { submitPublicFeedback, toggleSave } from "@/app/actions/workspace";
import { IDLE, type ActionState } from "@/services/forms/state";
import { publicationHref } from "@/services/links";
import { FEEDBACK_REASON_LABEL } from "@/services/workspace/types";
import type { PublicationTrace } from "@/types/api";

function Pending({ label, pendingLabel }: { label: string; pendingLabel: string }) {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="rounded border border-rule px-3 py-1.5 text-body-sm text-ink-secondary transition-colors hover:border-primary hover:text-primary disabled:opacity-60"
    >
      {pending ? pendingLabel : label}
    </button>
  );
}

function Result({ state }: { state: ActionState }) {
  if (state.status === "idle") return null;
  return (
    <p
      role="status"
      className={`text-body-sm ${
        state.status === "ok" ? "text-success-text" : "text-serious"
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
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:border-serious hover:text-serious"
      >
        Report a problem
      </button>
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
        <Pending label="Submit report" pendingLabel="Submitting…" />
        <button
          type="button"
          onClick={() => setOpen(false)}
          className="rounded px-3 py-1.5 text-body-sm text-muted hover:text-ink"
        >
          Cancel
        </button>
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
          <Link
            href={`/login?next=${encodeURIComponent(next)}`}
            className="rounded bg-primary px-3 py-1.5 text-body-sm font-semibold text-on-primary hover:bg-primary-hover"
          >
            Sign in
          </Link>
          <Link
            href={`/register?next=${encodeURIComponent(next)}`}
            className="rounded border border-rule px-3 py-1.5 text-body-sm text-ink-secondary hover:border-primary hover:text-primary"
          >
            Create an account
          </Link>
        </div>
        <div className="border-t border-rule pt-3">
          <FeedbackControl publicationKey={publicationKey} title={title} trace={trace} />
        </div>
      </div>
    );
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
