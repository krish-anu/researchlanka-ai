"use client";

import { useId, useMemo, useState, type ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { YearRangeInputs } from "@/components/ui/YearRangeInputs";
import {
  SoftNavForm,
  useFilterNavigation,
} from "@/components/navigation/FilterNavigation";
import type { SearchParams } from "@/services/filters";

const BASE_OMIT_KEYS = [
  "year_min",
  "year_max",
  "field",
  "page",
  "fields_page",
  "topics_page",
] as const;

function firstValue(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

function parseYear(value: string | number | undefined): number | undefined {
  if (value === undefined || value === "") return undefined;
  const parsed =
    typeof value === "number" ? value : Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function ResetFiltersButton({ href }: { href: string }) {
  const { navigate } = useFilterNavigation();
  return (
    <Button type="button" variant="ghost" size="sm" onClick={() => navigate(href)}>
      Reset
    </Button>
  );
}

function filtersHref(
  basePath: string,
  params: SearchParams,
  patch: { year_min?: number | ""; year_max?: number | ""; field?: string },
): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (
      ["year_min", "year_max", "field", "page", "fields_page", "topics_page"].includes(
        key,
      )
    ) {
      continue;
    }
    for (const item of Array.isArray(value) ? value : value ? [value] : []) {
      search.append(key, item);
    }
  }

  const yearMin =
    patch.year_min !== undefined
      ? patch.year_min
      : firstValue(params, "year_min");
  const yearMax =
    patch.year_max !== undefined
      ? patch.year_max
      : firstValue(params, "year_max");
  const field =
    patch.field !== undefined ? patch.field : firstValue(params, "field");

  if (yearMin !== "" && yearMin != null) search.set("year_min", String(yearMin));
  if (yearMax !== "" && yearMax != null) search.set("year_max", String(yearMax));
  if (field) search.set("field", field);

  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
}

function filterSummary({
  yearMin,
  yearMax,
  field,
  yearStart,
  yearEnd,
}: {
  yearMin?: number;
  yearMax?: number;
  field: string;
  yearStart?: number;
  yearEnd?: number;
}): string {
  const coversAll =
    yearStart != null &&
    yearEnd != null &&
    yearMin === yearStart &&
    yearMax === yearEnd;
  const years =
    yearMin == null && yearMax == null
      ? "All years"
      : coversAll
        ? `All years (${yearStart}–${yearEnd})`
        : yearMin != null && yearMax != null
          ? `${yearMin}–${yearMax}`
          : yearMin != null
            ? `From ${yearMin}`
            : `Through ${yearMax}`;
  const fieldLabel = field || "All fields";
  return `${years} · ${fieldLabel}`;
}

/**
 * Analytics filter card: year presets, dual year selects, searchable field,
 * optional extra controls, and either instant apply or an explicit Apply button.
 */
export function AnalyticsFiltersForm({
  params,
  fields,
  basePath,
  defaultFrom,
  defaultTo,
  yearStart,
  yearEnd,
  title = "Filters",
  summaryLabel = "Filters applied",
  extraControls,
  omitParamKeys = [],
  applyLabel,
}: {
  params: SearchParams;
  fields: string[];
  basePath: string;
  defaultFrom?: number;
  defaultTo?: number;
  yearStart?: number;
  yearEnd?: number;
  title?: string;
  summaryLabel?: string;
  /** Extra labeled controls rendered inside the same SoftNavForm. */
  extraControls?: ReactNode;
  /** Param keys rendered in `extraControls` — skip hidden duplicates. */
  omitParamKeys?: string[];
  /** When set, year/field changes wait for this Apply button instead of auto-submitting. */
  applyLabel?: string;
}) {
  const { navigate } = useFilterNavigation();
  const fieldListId = useId();
  const selected = firstValue(params, "field");
  const options = useMemo(
    () => [...new Set([...fields, ...(selected ? [selected] : [])])].sort(),
    [fields, selected],
  );
  const prefilledYears = defaultFrom != null || defaultTo != null;
  const yearMin =
    parseYear(firstValue(params, "year_min")) ??
    (prefilledYears ? defaultFrom : undefined);
  const yearMax =
    parseYear(firstValue(params, "year_max")) ??
    (prefilledYears ? defaultTo : undefined);
  const [fieldQuery, setFieldQuery] = useState(selected);
  const requireApply = Boolean(applyLabel);

  const summary = filterSummary({
    yearMin,
    yearMax,
    field: selected,
    yearStart,
    yearEnd,
  });

  const lastFiveFrom =
    yearStart != null && yearEnd != null
      ? Math.max(yearStart, yearEnd - 4)
      : undefined;

  const hiddenOmit = new Set<string>([...BASE_OMIT_KEYS, ...omitParamKeys]);

  return (
    <section className="analytics-filter-card panel" aria-label={title}>
      <div className="analytics-filter-card-head">
        <h2 className="analytics-filter-card-title">{title}</h2>
        <p className="analytics-filter-summary">
          <span className="text-muted">{summaryLabel}:</span> {summary}
        </p>
      </div>

      {yearStart != null && yearEnd != null ? (
        <div className="analytics-year-presets" role="group" aria-label="Year presets">
          <button
            type="button"
            className="analytics-year-chip"
            aria-pressed={
              yearMin === yearStart && yearMax === yearEnd ? true : undefined
            }
            onClick={() =>
              navigate(
                filtersHref(basePath, params, {
                  year_min: yearStart,
                  year_max: yearEnd,
                }),
              )
            }
          >
            All years
          </button>
          {lastFiveFrom != null ? (
            <button
              type="button"
              className="analytics-year-chip"
              aria-pressed={
                yearMin === lastFiveFrom && yearMax === yearEnd ? true : undefined
              }
              onClick={() =>
                navigate(
                  filtersHref(basePath, params, {
                    year_min: lastFiveFrom,
                    year_max: yearEnd,
                  }),
                )
              }
            >
              Last 5 years
            </button>
          ) : null}
          <button
            type="button"
            className="analytics-year-chip"
            aria-pressed={
              yearMin === yearEnd && yearMax === yearEnd ? true : undefined
            }
            onClick={() =>
              navigate(
                filtersHref(basePath, params, {
                  year_min: yearEnd,
                  year_max: yearEnd,
                }),
              )
            }
          >
            {yearEnd} only
          </button>
        </div>
      ) : null}

      <SoftNavForm action={basePath} className="analytics-filters">
        {Object.entries(params)
          .filter(([key]) => !hiddenOmit.has(key))
          .flatMap(([key, value]) =>
            (Array.isArray(value) ? value : value ? [value] : []).map(
              (item, index) => (
                <input
                  type="hidden"
                  name={key}
                  value={item}
                  key={`${key}-${index}`}
                />
              ),
            ),
          )}

        <YearRangeInputs
          startYear={yearStart}
          endYear={yearEnd}
          defaultFrom={firstValue(params, "year_min") || defaultFrom}
          defaultTo={firstValue(params, "year_max") || defaultTo}
          allowEmpty={!prefilledYears}
          autoSubmit={!requireApply}
        />

        <label className="analytics-field-label">
          Research field
          <input
            name="field"
            list={fieldListId}
            value={fieldQuery}
            autoComplete="off"
            placeholder="All fields — type to search"
            onChange={(event) => setFieldQuery(event.target.value)}
            onBlur={(event) => {
              if (requireApply) return;
              const next = event.target.value.trim();
              if (next === selected) return;
              event.currentTarget.form?.requestSubmit();
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                event.currentTarget.form?.requestSubmit();
              }
            }}
          />
          <datalist id={fieldListId}>
            {options.map((field) => (
              <option key={field} value={field} />
            ))}
          </datalist>
        </label>

        {Array.isArray(params.field)
          ? params.field.slice(1).map((field, index) => (
              <input
                type="hidden"
                key={`field-${index}`}
                name="field"
                value={field}
              />
            ))
          : null}

        {extraControls}

        <div className="analytics-filter-actions">
          {applyLabel ? (
            <Button type="submit" variant="primary" size="sm">
              {applyLabel}
            </Button>
          ) : null}
          <ResetFiltersButton href={basePath} />
        </div>
      </SoftNavForm>
    </section>
  );
}
