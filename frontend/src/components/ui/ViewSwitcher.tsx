"use client";
import { useState, type ReactNode } from "react";

export function ViewSwitcher({ cards, table, label, initialView = "cards" }: { cards: ReactNode; table: ReactNode; label: string; initialView?: "cards" | "table" }) {
  const [view, setView] = useState(initialView);
  return <div className="min-w-0"><div className="mb-4 flex justify-end"><div className="chart-segments" aria-label={label}><button type="button" aria-pressed={view === "cards"} onClick={() => setView("cards")}>Cards</button><button type="button" aria-pressed={view === "table"} onClick={() => setView("table")}>Table</button></div></div>{view === "cards" ? cards : table}</div>;
}
