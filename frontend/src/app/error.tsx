"use client";

import { useEffect } from "react";

/**
 * Last-resort boundary. Expected API failures are handled as values inside the
 * pages, so reaching here means a genuine rendering fault worth logging.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="panel mx-auto max-w-lg p-6">
      <h1 className="text-body-lg font-semibold text-ink">Something went wrong</h1>
      <p className="mt-2 text-body-sm text-ink-secondary">
        This page could not be rendered. The error has been logged to the server
        console.
      </p>
      {error.digest ? (
        <p className="mt-2 text-body-sm text-muted">
          Reference: <code className="rounded bg-wash px-1 py-0.5">{error.digest}</code>
        </p>
      ) : null}
      <button
        type="button"
        onClick={reset}
        className="mt-4 rounded border border-rule bg-wash px-3 py-1.5 text-body-sm font-medium text-ink hover:bg-page"
      >
        Try again
      </button>
    </div>
  );
}
