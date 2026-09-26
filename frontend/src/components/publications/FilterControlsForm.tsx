"use client";

import { Button } from "@/components/ui/Button";
import { YearRangeInputs } from "@/components/ui/YearRangeInputs";
import {
  SoftNavForm,
  SoftNavLink,
  useFilterNavigation,
} from "@/components/navigation/FilterNavigation";
import { REPEATABLE_FILTERS, toggleFilterHref, type SearchParams } from "@/services/filters";
import { titleCase } from "@/services/format";
import { SORT_OPTIONS } from "@/types/api";

function values(searchParams: SearchParams, key: string): string[] {
  const raw = searchParams[key];
  if (raw === undefined) return [];
  return (Array.isArray(raw) ? raw : [raw]).filter((item) => item !== "");
}

function first(searchParams: SearchParams, key: string): string {
  return values(searchParams, key)[0] ?? "";
}

function ResetFiltersButton({ href }: { href: string }) {
  const { navigate } = useFilterNavigation();
  return (
    <Button type="button" variant="ghost" onClick={() => navigate(href)}>
      Reset
    </Button>
  );
}

export function FilterControlsForm({
  searchParams,
  basePath,
  yearStart,
  yearEnd,
}: {
  searchParams: SearchParams;
  basePath: string;
  yearStart?: number;
  yearEnd?: number;
}) {
  const inputClass =
    "w-full rounded border border-rule bg-sunk px-2 py-1.5 text-body-sm text-ink focus:border-primary focus:outline-none";
  const labelClass = "label-caps flex flex-col gap-1.5 text-muted";

  return (
    <SoftNavForm action={basePath} className="panel flex flex-col gap-4 p-4">
      {first(searchParams, "q") ? (
        <input type="hidden" name="q" value={first(searchParams, "q")} />
      ) : null}
      {REPEATABLE_FILTERS.flatMap((name) =>
        values(searchParams, name).map((value) => (
          <input key={`${name}-${value}`} type="hidden" name={name} value={value} />
        )),
      )}

      <div className="grid grid-cols-2 gap-2">
        <YearRangeInputs
          startYear={yearStart}
          endYear={yearEnd}
          defaultFrom={first(searchParams, "year_min")}
          defaultTo={first(searchParams, "year_max")}
          inputClassName={inputClass}
          labelClassName={labelClass}
          allowEmpty
        />
      </div>

      <label className={labelClass}>
        Sort
        <select
          className={inputClass}
          name="sort"
          defaultValue={first(searchParams, "sort")}
        >
          <option value="">Default</option>
          {SORT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <fieldset className="flex flex-col gap-1.5">
        <legend className="label-caps pb-2 text-muted">Record properties</legend>
        {(
          [
            ["is_oa", "Open access only"],
            ["has_doi", "Has a DOI"],
            ["has_abstract", "Has an abstract"],
          ] as const
        ).map(([name, label]) => (
          <label
            key={name}
            className="flex items-center gap-2 text-body-sm text-ink-secondary"
          >
            <input
              type="checkbox"
              name={name}
              value="true"
              defaultChecked={first(searchParams, name) === "true"}
              className="size-4"
            />
            {label}
          </label>
        ))}
      </fieldset>

      <div className="flex gap-2">
        <Button type="submit" variant="primary" className="flex-1">
          Apply
        </Button>
        <ResetFiltersButton href={basePath} />
      </div>
    </SoftNavForm>
  );
}

export function ActiveFilters({
  searchParams,
  basePath = "/publications",
}: {
  searchParams: SearchParams;
  basePath?: string;
}) {
  const pills: { label: string; href: string; key: string }[] = [];

  for (const name of REPEATABLE_FILTERS) {
    for (const value of values(searchParams, name)) {
      pills.push({
        key: `${name}:${value}`,
        label: filterPillLabel(name, value),
        href: toggleFilterHref(basePath, searchParams, name, value),
      });
    }
  }

  for (const name of ["year_min", "year_max", "is_oa", "has_doi", "has_abstract"]) {
    const value = first(searchParams, name);
    if (!value) continue;
    pills.push({
      key: `${name}:${value}`,
      label: filterPillLabel(name, value),
      href: toggleFilterHref(basePath, searchParams, name, value),
    });
  }

  if (pills.length === 0) return null;

  return (
    <div className="active-filters-bar">
      <p className="active-filters-label">Active filters</p>
      <ul className="active-filters-list" aria-label="Active filters">
        {pills.map((pill) => (
          <li key={pill.key}>
            <SoftNavLink href={pill.href} className="chip chip-filter">
              {pill.label}
              <span aria-hidden className="text-muted">
                ✕
              </span>
              <span className="sr-only">Remove filter</span>
            </SoftNavLink>
          </li>
        ))}
      </ul>
      <SoftNavLink href={basePath} className="active-filters-clear">
        Clear all
      </SoftNavLink>
    </div>
  );
}

const FILTER_KEY_LABELS: Record<string, string> = {
  type: "Type",
  institution: "Institution",
  country: "Country",
  domain: "Domain",
  field: "Field",
  researcher: "Researcher",
  subfield: "Subfield",
  topic: "Topic",
  nmf_topic: "Topic model",
  nmf_topic_id: "Topic id",
  journal: "Journal",
  source_dataset: "Source",
  quality_flag: "Quality",
  scope: "Connections",
  min_weight: "Min shared pubs",
  limit: "Max nodes",
};

const SCOPE_VALUE_LABELS: Record<string, string> = {
  institution: "Institutions",
  researcher: "Researchers",
  country: "Countries",
};

/** Human-readable chip copy — never raw keys like `is_oa=true`. */
function filterPillLabel(name: string, value: string): string {
  if (name === "is_oa") {
    return value === "true" ? "Open access" : "Not open access";
  }
  if (name === "has_doi") {
    return value === "true" ? "Has a DOI" : "Missing DOI";
  }
  if (name === "has_abstract") {
    return value === "true" ? "Has an abstract" : "Missing abstract";
  }
  if (name === "year_min") return `From ${value}`;
  if (name === "year_max") return `To ${value}`;
  if (name === "scope") {
    return `Connections: ${SCOPE_VALUE_LABELS[value] ?? value}`;
  }

  const key =
    FILTER_KEY_LABELS[name] ?? titleCase(name.replaceAll("_", " "));
  return `${key}: ${value}`;
}
