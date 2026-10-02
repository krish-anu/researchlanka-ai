"use client";

import type { ChangeEvent } from "react";

function parseYear(value: string | number | undefined): number | undefined {
  if (value === undefined || value === "") return undefined;
  const parsed =
    typeof value === "number" ? value : Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function clampYear(value: number, start: number, end: number): number {
  return Math.min(end, Math.max(start, value));
}

function yearOptions(start: number, end: number): number[] {
  const years: number[] = [];
  for (let year = start; year <= end; year += 1) years.push(year);
  return years;
}

function enforceYearOrder(
  form: HTMLFormElement,
  fromName: string,
  toName: string,
  changed: "from" | "to",
) {
  const fromEl = form.elements.namedItem(fromName);
  const toEl = form.elements.namedItem(toName);
  if (
    !(fromEl instanceof HTMLSelectElement || fromEl instanceof HTMLInputElement) ||
    !(toEl instanceof HTMLSelectElement || toEl instanceof HTMLInputElement)
  ) {
    return;
  }

  const fromYear = parseYear(fromEl.value);
  const toYear = parseYear(toEl.value);
  if (fromYear == null || toYear == null || fromYear <= toYear) return;

  if (changed === "from") toEl.value = String(fromYear);
  else fromEl.value = String(toYear);
}

/**
 * Year-from / year-to controls bounded by dataset coverage.
 * Uses selects when coverage is known (closed range); number inputs otherwise.
 * Keeps from ≤ to, and can auto-submit the parent GET form on change.
 */
export function YearRangeInputs({
  startYear,
  endYear,
  defaultFrom,
  defaultTo,
  fromName = "year_min",
  toName = "year_max",
  fromLabel = "Year from",
  toLabel = "Year to",
  inputClassName,
  labelClassName,
  allowEmpty = true,
  autoSubmit = false,
}: {
  startYear?: number;
  endYear?: number;
  defaultFrom?: number | string;
  defaultTo?: number | string;
  fromName?: string;
  toName?: string;
  fromLabel?: string;
  toLabel?: string;
  inputClassName?: string;
  labelClassName?: string;
  allowEmpty?: boolean;
  autoSubmit?: boolean;
}) {
  const hasCoverage =
    typeof startYear === "number" &&
    typeof endYear === "number" &&
    startYear <= endYear;
  const lo = hasCoverage ? startYear : undefined;
  const hi = hasCoverage ? endYear : undefined;

  const initialFrom = (() => {
    let year = parseYear(defaultFrom);
    if (year != null && lo != null && hi != null) year = clampYear(year, lo, hi);
    return year;
  })();

  const initialTo = (() => {
    let year = parseYear(defaultTo);
    if (year != null && lo != null && hi != null) year = clampYear(year, lo, hi);
    if (year != null && initialFrom != null && year < initialFrom) return initialFrom;
    return year;
  })();

  const onChange = (
    event: ChangeEvent<HTMLSelectElement | HTMLInputElement>,
    changed: "from" | "to",
  ) => {
    const form = event.currentTarget.form;
    if (!form) return;
    enforceYearOrder(form, fromName, toName, changed);
    if (autoSubmit) form.requestSubmit();
  };

  if (hasCoverage && lo != null && hi != null) {
    const years = yearOptions(lo, hi);
    return (
      <>
        <label className={labelClassName}>
          {fromLabel}
          <select
            className={inputClassName}
            name={fromName}
            defaultValue={initialFrom != null ? String(initialFrom) : ""}
            onChange={(event) => onChange(event, "from")}
          >
            {allowEmpty ? <option value="">Any</option> : null}
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClassName}>
          {toLabel}
          <select
            className={inputClassName}
            name={toName}
            defaultValue={initialTo != null ? String(initialTo) : ""}
            onChange={(event) => onChange(event, "to")}
          >
            {allowEmpty ? <option value="">Any</option> : null}
            {years.map((year) => (
              <option key={year} value={year}>
                {year}
              </option>
            ))}
          </select>
        </label>
      </>
    );
  }

  return (
    <>
      <label className={labelClassName}>
        {fromLabel}
        <input
          className={inputClassName}
          type="number"
          name={fromName}
          inputMode="numeric"
          defaultValue={initialFrom != null ? String(initialFrom) : ""}
          onChange={(event) => onChange(event, "from")}
        />
      </label>
      <label className={labelClassName}>
        {toLabel}
        <input
          className={inputClassName}
          type="number"
          name={toName}
          inputMode="numeric"
          defaultValue={initialTo != null ? String(initialTo) : ""}
          onChange={(event) => onChange(event, "to")}
        />
      </label>
    </>
  );
}
