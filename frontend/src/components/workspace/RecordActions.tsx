"use client";

import Link from "next/link";
import { useActionState, useState } from "react";
import { useFormStatus } from "react-dom";

import { submitFlag, toggleSave } from "@/app/actions/workspace";
import { IDLE, type ActionState } from "@/services/forms/state";
import { FLAG_REASON_LABEL } from "@/services/workspace/types";

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

function FlagControl({
  publicationKey,
  title,
}: {
  publicationKey: string;
  title: string;
}) {
  const [state, formAction] = useActionState(submitFlag, IDLE);
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
        Flag this record
      </button>
    );
  }

  return (
    <form action={formAction} className="flex w-full flex-col gap-3">
      <input type="hidden" name="publication_key" value={publicationKey} />
      <input type="hidden" name="title" value={title} />

      <label className="flex flex-col gap-1.5">
        <span className="label-caps text-muted">What looks wrong?</span>
        <select
          name="reason"
          required
          defaultValue="wrong_metadata"
          className="rounded border border-rule bg-surface px-3 py-2 text-body-sm text-ink"
        >
          {Object.entries(FLAG_REASON_LABEL).map(([value, label]) => (
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
        Flags queue a record for an administrator to check. The pipeline owns
        the data, so nothing you submit edits the record directly.
      </p>
    </form>
  );
}

/**
 * Save and flag, or the reason a visitor cannot use them.
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
}: {
  publicationKey: string;
  title: string;
  signedIn: boolean;
  initiallySaved: boolean;
}) {
  if (!signedIn) {
    const next = `/publications/${publicationKey}`;
    return (
      <div className="panel flex flex-col gap-2 p-4">
        <p className="text-body-sm text-ink-secondary">
          Reading this record needs no account. Signing in adds a saved library
          and lets you flag it if the metadata is wrong.
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
        <FlagControl publicationKey={publicationKey} title={title} />
      </div>
    </div>
  );
}
