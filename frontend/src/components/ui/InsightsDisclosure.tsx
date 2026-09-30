"use client";

import { useState, type ReactNode } from "react";

/**
 * Collapsible insights block for directory pages — keeps charts off the
 * scan path until the reader asks for them.
 */
export function InsightsDisclosure({
  title = "Insights",
  description,
  children,
  defaultOpen = false,
}: {
  title?: string;
  description?: string;
  children: ReactNode;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <details
      className="insights-disclosure panel overflow-hidden"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer list-none px-4 py-3 [&::-webkit-details-marker]:hidden">
        <span className="flex flex-wrap items-baseline justify-between gap-2">
          <span>
            <span className="font-medium text-ink">{title}</span>
            {description ? (
              <span className="mt-0.5 block text-body-sm text-ink-secondary">
                {description}
              </span>
            ) : null}
          </span>
          <span className="text-body-sm text-primary">
            {open ? "Hide charts ↑" : "Show charts ↓"}
          </span>
        </span>
      </summary>
      {open ? <div className="border-t border-rule px-4 py-4">{children}</div> : null}
    </details>
  );
}
