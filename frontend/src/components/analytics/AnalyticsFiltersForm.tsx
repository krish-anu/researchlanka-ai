"use client";

import { useEffect, useId, useMemo, useState, type ReactNode } from "react";

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

export type FilterChoice = { label: string; count: number };

function choicesFrom(
  values: Array<string | FilterChoice> | undefined,
): FilterChoice[] {
  const seen = new Set<string>();
  const choices: FilterChoice[] = [];
  for (const value of values ?? []) {
    const choice = typeof value === "string" ? { label: value, count: 1 } : value;
    if (!choice.label || choice.count <= 0 || seen.has(choice.label)) continue;
    seen.add(choice.label);
    choices.push(choice);
  }
  return choices;
}

/** Prefix, then word start, then contains. Empty query keeps count order. */
function rankChoices(options: FilterChoice[], query: string, limit = 8): FilterChoice[] {
  const q = query.trim().toLowerCase();
  if (!q) return options.slice(0, limit);
  const scored = options.flatMap((option) => {
    const label = option.label.toLowerCase();
    const words = label.split(/[^a-z0-9]+/);
    const rank = label.startsWith(q)
      ? 0
      : words.some((word) => word.startsWith(q))
        ? 1
        : label.includes(q)
          ? 2
          : -1;
    return rank < 0 ? [] : [{ option, rank }];
  });
  scored.sort(
    (a, b) =>
      a.rank - b.rank ||
      b.option.count - a.option.count ||
      a.option.label.localeCompare(b.option.label),
  );
  return scored.slice(0, limit).map((item) => item.option);
}

/** Keep the current value visible when filters drop it from the ranked list. */
function withCurrentChoice(
  matches: FilterChoice[],
  selected: string,
  query: string,
): FilterChoice[] {
  const current = selected.trim();
  if (!current) return matches;
  const q = query.trim().toLowerCase();
  if (q && !current.toLowerCase().includes(q)) return matches;
  if (matches.some((item) => item.label === current)) return matches;
  return [{ label: current, count: 0 }, ...matches].slice(0, 8);
}

function parseYear(value: string | number | undefined): number | undefined {
  if (value === undefined || value === "") return undefined;
  const parsed =
    typeof value === "number" ? value : Number.parseInt(String(value), 10);
  return Number.isFinite(parsed) ? parsed : undefined;
}

function ResetFiltersButton({
  href,
  label = "Reset",
}: {
  href: string;
  label?: string;
}) {
  const { navigate } = useFilterNavigation();
  return (
    <Button type="button" variant="ghost" size="sm" onClick={() => navigate(href)}>
      {label}
    </Button>
  );
}

function CountBoundControl({
  minCount,
  requireApply,
}: {
  minCount: string;
  maxCount: string;
  requireApply: boolean;
}) {
  const [draft, setDraft] = useState(minCount);
  const [error, setError] = useState("");

  function commit(form: HTMLFormElement | null) {
    const trimmed = draft.trim();
    if (trimmed !== "" && !/^[1-9]\d*$/.test(trimmed)) {
      setError("Enter a whole number of 1 or more, or leave this blank.");
      return;
    }
    setError("");
    if (!form || requireApply) return;
    form
      .querySelectorAll('input[type="hidden"][name="min_count"], input[type="hidden"][name="max_count"]')
      .forEach((node) => node.remove());
    form.requestSubmit();
  }

  return (
    <label className="analytics-field-label">
      At least
      <input
        name={/^[1-9]\d*$/.test(draft.trim()) ? "min_count" : undefined}
        value={draft}
        inputMode="numeric"
        placeholder="All publication counts"
        aria-label="Minimum publications"
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? "min-count-error" : undefined}
        onChange={(event) => {
          setDraft(event.target.value);
          setError("");
        }}
        onBlur={(event) => commit(event.currentTarget.form)}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          commit(event.currentTarget.form);
        }}
      />
      {error ? (
        <span id="min-count-error" className="text-label text-serious" role="alert">
          {error}
        </span>
      ) : null}
    </label>
  );
}

function RefineGroup({
  title,
  enabled,
  children,
}: {
  title: string;
  enabled: boolean;
  children: ReactNode;
}) {
  if (!enabled) return <>{children}</>;
  return (
    <details
      className="refine-disclosure border-b border-rule"
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !event.currentTarget.open) return;
        const target = event.target;
        if (!(target instanceof HTMLElement)) return;
        if (target.closest(".filter-suggest")) return;
        event.preventDefault();
        event.currentTarget.open = false;
        event.currentTarget.querySelector("summary")?.focus();
      }}
    >
      <summary className="flex min-h-11 cursor-pointer items-center justify-between gap-2 py-2 text-body-sm font-medium text-ink">
        {title}
      </summary>
      <div className="flex flex-col gap-2 pb-3">{children}</div>
    </details>
  );
}

function closeEnclosingFilter(event: {
  key: string;
  preventDefault: () => void;
  currentTarget: HTMLElement;
}) {
  if (event.key !== "Escape") return false;
  event.preventDefault();
  const details = event.currentTarget.closest("details");
  if (details?.open) {
    details.open = false;
    details.querySelector("summary")?.focus();
  }
  return true;
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
  yearPhrase,
  institution,
}: {
  yearMin?: number;
  yearMax?: number;
  field: string;
  yearStart?: number;
  yearEnd?: number;
  yearPhrase?: string;
  institution?: string;
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
  const yearText = yearPhrase
    ? years.startsWith("All years")
      ? years.replace("All years", `${yearPhrase}, all years`)
      : `${yearPhrase} ${years}`
    : years;
  const parts = [yearText, field || "All fields"];
  if (institution) parts.push(`Institution on the publication: ${institution}`);
  return parts.join(" · ");
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
  institutions,
  yearPhrase,
  fromLabel = "Year from",
  toLabel = "Year to",
  showMinCount = false,
  layout = "card",
  deferUntilField = false,
}: {
  params: SearchParams;
  fields: Array<string | FilterChoice>;
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
  /** Institution names for the publication-affiliation control. Omit to hide it. */
  institutions?: Array<string | FilterChoice>;
  /** Prefixes the year portion of the summary, e.g. "Publication years". */
  yearPhrase?: string;
  fromLabel?: string;
  toLabel?: string;
  /** Ranked directories: keep rows with at least this many publications. */
  showMinCount?: boolean;
  layout?: "card" | "refine";
  /** Overview: year changes wait until a research field, or All fields, is chosen. */
  deferUntilField?: boolean;
}) {
  const { navigate } = useFilterNavigation();
  const fieldListId = useId();
  const institutionListId = useId();
  const selected = firstValue(params, "field");
  const [fieldGate, setFieldGate] = useState(Boolean(selected));
  const selectedInstitution = firstValue(params, "institution");
  const options = useMemo(() => choicesFrom(fields), [fields]);
  const prefilledYears = defaultFrom != null || defaultTo != null;
  const yearMin =
    parseYear(firstValue(params, "year_min")) ??
    (prefilledYears ? defaultFrom : undefined);
  const yearMax =
    parseYear(firstValue(params, "year_max")) ??
    (prefilledYears ? defaultTo : undefined);
  const [fieldQuery, setFieldQuery] = useState(selected);
  const [fieldOpen, setFieldOpen] = useState(false);
  const [fieldDirty, setFieldDirty] = useState(false);
  const [institutionQuery, setInstitutionQuery] = useState(selectedInstitution);
  const [institutionOpen, setInstitutionOpen] = useState(false);
  const [institutionDirty, setInstitutionDirty] = useState(false);
  const requireApply = Boolean(applyLabel);

  useEffect(() => {
    setFieldQuery(selected);
    setInstitutionQuery(selectedInstitution);
    setFieldDirty(false);
    setInstitutionDirty(false);
  }, [selected, selectedInstitution]);
  const selectedMinCount = firstValue(params, "min_count");

  const summary = filterSummary({
    yearMin,
    yearMax,
    field: selected,
    yearStart,
    yearEnd,
    yearPhrase,
    institution: institutions ? selectedInstitution : undefined,
  });

  const lastFiveFrom =
    yearStart != null && yearEnd != null
      ? Math.max(yearStart, yearEnd - 4)
      : undefined;

  const hiddenOmit = new Set<string>([...BASE_OMIT_KEYS, ...omitParamKeys]);
  if (institutions) hiddenOmit.add("institution");
  if (showMinCount) hiddenOmit.add("min_count");
  hiddenOmit.add("max_count");
  const institutionOptions = useMemo(
    () => choicesFrom(institutions),
    [institutions],
  );
  const fieldQueryText = fieldDirty ? fieldQuery : "";
  const institutionQueryText = institutionDirty ? institutionQuery : "";
  const fieldMatches = useMemo(
    () => withCurrentChoice(rankChoices(options, fieldQueryText), selected, fieldQueryText),
    [options, fieldQueryText, selected],
  );
  const institutionMatches = useMemo(
    () =>
      withCurrentChoice(
        rankChoices(institutionOptions, institutionQueryText),
        selectedInstitution,
        institutionQueryText,
      ),
    [institutionOptions, institutionQueryText, selectedInstitution],
  );

  const refine = layout === "refine";
  const yearPresets =
    yearStart != null && yearEnd != null ? (
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
      ) : null;

  return (
    <section
      className={refine ? undefined : "analytics-filter-card panel"}
      aria-label={refine ? undefined : title}
    >
      {refine ? null : (
        <div className="analytics-filter-card-head">
          <p className="analytics-filter-card-title">{title}</p>
          <p className="analytics-filter-summary">
            <span className="text-muted">{summaryLabel}:</span> {summary}
          </p>
        </div>
      )}

      {refine ? null : yearPresets}

      <SoftNavForm action={basePath} className={refine ? "refine-filters" : "analytics-filters"}>
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

        <RefineGroup title={yearPhrase ?? "Publication years"} enabled={refine}>
          {refine ? yearPresets : null}
          <YearRangeInputs
            key={`${firstValue(params, "year_min") || defaultFrom || "any"}-${firstValue(params, "year_max") || defaultTo || "any"}`}
            startYear={yearStart}
            endYear={yearEnd}
            defaultFrom={firstValue(params, "year_min") || defaultFrom}
            defaultTo={firstValue(params, "year_max") || defaultTo}
            fromLabel={fromLabel}
            toLabel={toLabel}
            labelClassName={refine ? "analytics-field-label" : undefined}
            allowEmpty={!prefilledYears}
            autoSubmit={!requireApply && (!deferUntilField || fieldGate)}
          />
        </RefineGroup>

        <RefineGroup title="Research field" enabled={refine}>
        <label className="analytics-field-label relative">
          <span className={refine ? "sr-only" : undefined}>Research field</span>
          <input
            name="field"
            role="combobox"
            aria-expanded={fieldOpen}
            aria-controls={fieldListId}
            aria-autocomplete="list"
            value={fieldQuery}
            autoComplete="off"
            placeholder="Type field name"
            onChange={(event) => {
              setFieldDirty(true);
              setFieldQuery(event.target.value);
              setFieldOpen(true);
            }}
            onFocus={() => setFieldOpen(true)}
            onBlur={(event) => {
              const typed = event.target.value.trim();
              const exact = options.find(
                (field) => field.label.toLowerCase() === typed.toLowerCase(),
              );
              window.setTimeout(() => setFieldOpen(false), 120);
              if (requireApply) return;
              if (!typed) {
                if (selected) event.currentTarget.form?.requestSubmit();
                return;
              }
              if (!exact) {
                setFieldQuery(selected);
                setFieldDirty(false);
                return;
              }
              if (exact.label !== selected) {
                setFieldGate(true);
                setFieldQuery(exact.label);
                event.currentTarget.value = exact.label;
                event.currentTarget.form?.requestSubmit();
              }
            }}
            onKeyDown={(event) => {
              if (event.key === "Escape") {
                if (fieldOpen) {
                  event.preventDefault();
                  event.stopPropagation();
                  setFieldOpen(false);
                  return;
                }
                closeEnclosingFilter(event);
                return;
              }
              if (event.key !== "Enter") return;
              event.preventDefault();
              const typed = event.currentTarget.value.trim();
              const exact = options.find(
                (field) => field.label.toLowerCase() === typed.toLowerCase(),
              );
              const chosen =
                exact?.label ??
                (fieldMatches.length === 1 ? fieldMatches[0].label : undefined);
              if (!typed) {
                setFieldGate(true);
                setFieldQuery("");
                event.currentTarget.value = "";
                event.currentTarget.form?.requestSubmit();
                return;
              }
              if (!chosen) return;
              setFieldGate(true);
              setFieldQuery(chosen);
              event.currentTarget.value = chosen;
              event.currentTarget.form?.requestSubmit();
            }}
          />
          {fieldOpen ? (
            <ul id={fieldListId} role="listbox" className="filter-suggest">
              <li>
                <button
                  type="button"
                  role="option"
                  onMouseDown={(event) => {
                    event.preventDefault();
                    setFieldGate(true);
                    setFieldQuery("");
                    setFieldDirty(false);
                    const input = event.currentTarget
                      .closest("label")
                      ?.querySelector("input");
                    if (input) input.value = "";
                    setFieldOpen(false);
                    if (!requireApply) input?.form?.requestSubmit();
                  }}
                >
                  All fields
                </button>
              </li>
              {fieldMatches.length ? (
                fieldMatches.map((field) => (
                  <li key={field.label}>
                    <button
                      type="button"
                      role="option"
                      onMouseDown={(event) => {
                        event.preventDefault();
                        setFieldGate(true);
                        setFieldQuery(field.label);
                        const input = event.currentTarget
                          .closest("label")
                          ?.querySelector("input");
                        if (input) input.value = field.label;
                        setFieldOpen(false);
                        if (!requireApply) {
                          input?.form?.requestSubmit();
                        }
                      }}
                    >
                      {field.label}
                    </button>
                  </li>
                ))
              ) : (
                <li className="filter-suggest-empty">No matching fields</li>
              )}
            </ul>
          ) : null}
        </label>
        </RefineGroup>

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

        {institutions ? (
          <RefineGroup title="Institution" enabled={refine}>
          <label className="analytics-field-label relative">
            <span className={refine ? "sr-only" : undefined}>
              Institution on the publication
            </span>
            <input
              name="institution"
              role="combobox"
              aria-expanded={institutionOpen}
              aria-controls={institutionListId}
              aria-autocomplete="list"
              value={institutionQuery}
              autoComplete="off"
              placeholder="Type institution name"
              onChange={(event) => {
                setInstitutionDirty(true);
                setInstitutionQuery(event.target.value);
                setInstitutionOpen(true);
              }}
              onFocus={() => setInstitutionOpen(true)}
              onBlur={(event) => {
                const typed = event.target.value.trim();
                const exact = institutionOptions.find(
                  (name) => name.label.toLowerCase() === typed.toLowerCase(),
                );
                window.setTimeout(() => setInstitutionOpen(false), 120);
                if (requireApply) return;
                if (!typed) {
                  if (selectedInstitution) event.currentTarget.form?.requestSubmit();
                  return;
                }
                if (!exact) {
                  setInstitutionQuery(selectedInstitution);
                  setInstitutionDirty(false);
                  return;
                }
                if (exact.label !== selectedInstitution) {
                  setInstitutionQuery(exact.label);
                  event.currentTarget.value = exact.label;
                  event.currentTarget.form?.requestSubmit();
                }
              }}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  if (institutionOpen) {
                    event.preventDefault();
                    event.stopPropagation();
                    setInstitutionOpen(false);
                    return;
                  }
                  closeEnclosingFilter(event);
                  return;
                }
                if (event.key !== "Enter") return;
                event.preventDefault();
                const typed = event.currentTarget.value.trim();
                const exact = institutionOptions.find(
                  (name) => name.label.toLowerCase() === typed.toLowerCase(),
                );
                const chosen =
                  exact?.label ??
                  (institutionMatches.length === 1 ? institutionMatches[0].label : undefined);
                if (!typed) {
                  setInstitutionQuery("");
                  event.currentTarget.value = "";
                  event.currentTarget.form?.requestSubmit();
                  return;
                }
                if (!chosen) return;
                setInstitutionQuery(chosen);
                event.currentTarget.value = chosen;
                event.currentTarget.form?.requestSubmit();
              }}
            />
            {institutionOpen ? (
              <ul id={institutionListId} role="listbox" className="filter-suggest">
                {institutionMatches.length ? (
                  institutionMatches.map((name) => (
                    <li key={name.label}>
                      <button
                        type="button"
                        role="option"
                        onMouseDown={(event) => {
                          event.preventDefault();
                          setInstitutionQuery(name.label);
                          const input = event.currentTarget
                            .closest("label")
                            ?.querySelector("input");
                          if (input) input.value = name.label;
                          setInstitutionOpen(false);
                          if (!requireApply) input?.form?.requestSubmit();
                        }}
                      >
                        {name.label}
                      </button>
                    </li>
                  ))
                ) : (
                  <li className="filter-suggest-empty">No matching institutions</li>
                )}
              </ul>
            ) : null}
          </label>
          </RefineGroup>
        ) : null}

        {showMinCount ? (
          <RefineGroup title="Publications" enabled={refine}>
          <CountBoundControl
            minCount={selectedMinCount}
            maxCount={firstValue(params, "max_count")}
            requireApply={requireApply}
          />
          </RefineGroup>
        ) : null}

        {Array.isArray(params.institution)
          ? params.institution.slice(1).map((name, index) => (
            <input
              type="hidden"
              key={`institution-${index}`}
              name="institution"
              value={name}
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
          <ResetFiltersButton href={basePath} label={refine ? "Clear all" : "Reset"} />
        </div>
      </SoftNavForm>
    </section>
  );
}
