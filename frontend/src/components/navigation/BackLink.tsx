"use client";

import { useRouter } from "next/navigation";

/** Returns to the previous list, including its filters, when that page is still in history. */
export function BackLink({
  fallback,
  label = "Back",
}: {
  fallback: string;
  label?: string;
}) {
  const router = useRouter();

  return (
    <button
      type="button"
      className="inline-flex min-h-11 items-center gap-1 text-body-sm text-ink-secondary hover:text-ink"
      onClick={() => {
        if (window.history.length > 1) router.back();
        else router.push(fallback);
      }}
    >
      <span aria-hidden>←</span>
      {label}
    </button>
  );
}
