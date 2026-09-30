"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { RankingBarChart } from "@/components/charts/RankingBarChart";
import { InstitutionScatterChart, type InstitutionPoint } from "@/components/charts/InstitutionScatterChart";
import { Button } from "@/components/ui/Button";

const MAX_COMPARE = 3;

type CompareContextValue = {
  selected: string[];
  max: number;
  toggle: (label: string) => void;
  remove: (label: string) => void;
  clear: () => void;
  isSelected: (label: string) => boolean;
  canSelectMore: boolean;
};

const CompareContext = createContext<CompareContextValue | null>(null);

export function useInstitutionCompare() {
  const value = useContext(CompareContext);
  if (!value) {
    throw new Error("useInstitutionCompare must be used within InstitutionCompareProvider");
  }
  return value;
}

export function InstitutionCompareProvider({ children }: { children: ReactNode }) {
  const [selected, setSelected] = useState<string[]>([]);

  const toggle = useCallback((label: string) => {
    setSelected((current) => {
      if (current.includes(label)) {
        return current.filter((item) => item !== label);
      }
      if (current.length >= MAX_COMPARE) return current;
      return [...current, label];
    });
  }, []);

  const remove = useCallback((label: string) => {
    setSelected((current) => current.filter((item) => item !== label));
  }, []);

  const clear = useCallback(() => setSelected([]), []);

  const value = useMemo<CompareContextValue>(
    () => ({
      selected,
      max: MAX_COMPARE,
      toggle,
      remove,
      clear,
      isSelected: (label: string) => selected.includes(label),
      canSelectMore: selected.length < MAX_COMPARE,
    }),
    [selected, toggle, remove, clear],
  );

  return (
    <CompareContext.Provider value={value}>
      {children}
      <CompareTray />
    </CompareContext.Provider>
  );
}

/** Checkbox to add/remove an institution from the compare selection (max 3). */
export function CompareCheckbox({
  label,
  showLabel = false,
}: {
  label: string;
  showLabel?: boolean;
}) {
  const { isSelected, toggle, canSelectMore } = useInstitutionCompare();
  const checked = isSelected(label);
  const disabled = !checked && !canSelectMore;
  const id = `compare-${label.replace(/\W+/g, "-").toLowerCase()}`;

  return (
    <label
      htmlFor={id}
      className={`inline-flex items-center gap-2 ${
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer"
      }`}
    >
      <input
        id={id}
        type="checkbox"
        className="size-4 accent-primary"
        checked={checked}
        disabled={disabled}
        onChange={() => toggle(label)}
        aria-label={showLabel ? undefined : `Compare ${label}`}
      />
      {showLabel ? (
        <span className="text-body-sm text-ink-secondary line-clamp-1">{label}</span>
      ) : (
        <span className="sr-only">Compare</span>
      )}
    </label>
  );
}

function scopedLabels<T extends { label: string }>(rows: T[], selected: string[]): T[] {
  if (selected.length === 0) return rows;
  return rows.filter((row) => selected.includes(row.label));
}

/** Bar chart of the page, or only the institutions ticked for comparison. */
export function ScopedInstitutionBars({
  entries,
}: {
  entries: { label: string; value: number; href?: string }[];
}) {
  const { selected } = useInstitutionCompare();
  const shown = scopedLabels(entries, selected);
  if (shown.length === 0) {
    return (
      <p className="text-body-sm text-muted">
        None of the compared institutions are on this page.
      </p>
    );
  }
  return (
    <RankingBarChart
      entries={shown}
      valueLabel="Publications"
      ariaLabel="Bar chart of publications by institution"
    />
  );
}

export function ScopedAccessibilityChart({ points }: { points: InstitutionPoint[] }) {
  const { selected } = useInstitutionCompare();
  return <InstitutionScatterChart points={scopedLabels(points, selected)} />;
}

/** Compact checklist for chart rows (top institutions). */
export function ComparePickList({ labels }: { labels: string[] }) {
  if (labels.length === 0) return null;

  return (
    <ul
      className="compare-pick-list"
      aria-label="Select institutions from the chart to compare"
    >
      {labels.map((label) => (
        <li key={label}>
          <CompareCheckbox label={label} showLabel />
        </li>
      ))}
    </ul>
  );
}

function compareHref(selected: string[]): string {
  const search = new URLSearchParams();
  for (const label of selected) {
    search.append("institution", label);
  }
  return `/institutions/compare?${search.toString()}`;
}

function CompareTray() {
  const { selected, remove, clear, max } = useInstitutionCompare();

  if (selected.length === 0) return null;

  const ready = selected.length >= 2;

  return (
    <div className="compare-tray" role="region" aria-label="Compare selection">
      <div className="compare-tray-panel panel">
        <div className="compare-tray-copy">
          <p className="compare-tray-title">
            {selected.length} of {max} selected
          </p>
          <ul className="compare-tray-chips">
            {selected.map((label) => (
              <li key={label}>
                <button
                  type="button"
                  className="chip chip-filter"
                  onClick={() => remove(label)}
                >
                  <span className="line-clamp-1 max-w-48">{label}</span>
                  <span aria-hidden className="text-muted">
                    ✕
                  </span>
                  <span className="sr-only">Remove {label}</span>
                </button>
              </li>
            ))}
          </ul>
          {!ready ? (
            <p className="compare-tray-hint">Select at least one more to compare</p>
          ) : null}
        </div>
        <div className="compare-tray-actions">
          <Button type="button" variant="ghost" size="sm" onClick={clear}>
            Clear
          </Button>
          {ready ? (
            <Button href={compareHref(selected)} variant="primary" size="sm">
              Compare selected
            </Button>
          ) : (
            <Button type="button" variant="primary" size="sm" disabled>
              Compare selected
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
