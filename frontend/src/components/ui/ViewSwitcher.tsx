"use client";

import { useEffect, useState, type ReactNode } from "react";

const STORAGE_KEY = "researchlanka-directory-view";

export function ViewSwitcher({
  cards,
  table,
  label,
  initialView = "cards",
  className = "",
  /** Persist Cards/Table choice across directory pages. */
  persistKey = "default",
  /** `inline` sits in the results toolbar. `sticky` stays above a long list. */
  chrome = "sticky",
  leading,
  extra,
  cardsLabel = "Cards",
}: {
  cards: ReactNode;
  table: ReactNode;
  label: string;
  initialView?: "cards" | "table";
  className?: string;
  persistKey?: string;
  chrome?: "sticky" | "inline";
  leading?: ReactNode;
  /** Controls rendered beside the Cards/Table switch, such as sort. */
  extra?: ReactNode;
  /** Visible name for the non-table view. */
  cardsLabel?: string;
}) {
  const [view, setView] = useState<"cards" | "table">(initialView);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(`${STORAGE_KEY}:${persistKey}`);
      if (saved === "cards" || saved === "table") setView(saved);
    } catch {
      /* storage may be disabled */
    }
    setHydrated(true);
  }, [persistKey]);

  const choose = (next: "cards" | "table") => {
    setView(next);
    try {
      window.localStorage.setItem(`${STORAGE_KEY}:${persistKey}`, next);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className={`min-w-0 ${className}`.trim()} data-view-ready={hydrated || undefined}>
      <div
        className={
          chrome === "inline"
            ? "mb-3 flex flex-wrap items-end justify-between gap-3"
            : "sticky top-16 z-[5] mb-4 flex justify-end bg-page/90 py-1 backdrop-blur-sm md:top-19"
        }
      >
        {leading ? <div className="min-w-0 flex-1">{leading}</div> : null}
        <div className="flex flex-wrap items-center gap-2">
        {extra}
        <div className="chart-segments" aria-label={label}>
          <button
            type="button"
            aria-pressed={view === "cards"}
            onClick={() => choose("cards")}
          >
            {cardsLabel}
          </button>
          <button
            type="button"
            aria-pressed={view === "table"}
            onClick={() => choose("table")}
          >
            Table
          </button>
        </div>
        </div>
      </div>
      {view === "cards" ? cards : table}
    </div>
  );
}
