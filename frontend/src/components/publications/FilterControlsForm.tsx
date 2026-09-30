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
import { SORT_OPTIONS, type Facets } from "@/types/api";

function values(searchParams: SearchParams, key: string): string[] {
  const raw = searchParams[key];
  if (raw === undefined) return [];
  return (Array.isArray(raw) ? raw : [raw]).filter((item) => item !== "");
}

function first(searchParams: SearchParams, key: string): string {
  return values(searchParams, key)[0] ?? "";
}

const APPLY_FACETS = ["type", "institution", "journal"] as const;

function FacetSelect({
  name,
  label,
  values,
  current,
}: {
  name: string;
  label: string;
  values: Record<string, number>;
  current: string;
}) {
  const entries = Object.entries(values)
    .filter(([value]) => value !== "")
    .sort((a, b) => b[1] - a[1]);
  if (entries.length === 0) return null;
  return (
    <label className="flex flex-col gap-1 border-b border-rule py-2 text-body-sm text-ink-secondary">
      {label}
      <select
        name={name}
        defaultValue={current}
        aria-label={label}
        className="min-h-11 rounded border border-rule bg-surface px-2 text-body-sm text-ink"
      >
        <option value="">All</option>
        {current && !entries.some(([value]) => value === current) ? (
          <option value={current}>{current}</option>
        ) : null}
        {entries.map(([value, count]) => (
          <option key={value} value={value}>
            {titleCase(value)} ({count})
          </option>
        ))}
      </select>
    </label>
  );
}

function ResetFiltersButton({ href }: { href: string }) {
  const { navigate } = useFilterNavigation();
  return (
    <Button type="button" variant="ghost" onClick={() => navigate(href)}>
      Clear all
    </Button>
  );
}

export function FilterControlsForm({
  searchParams,
  basePath,
  yearStart,
  yearEnd,
  facets,
}: {
  searchParams: SearchParams;
  basePath: string;
  yearStart?: number;
  yearEnd?: number;
  facets?: Facets;
}) {
  const inputClass =
    "min-h-11 w-full rounded border border-rule bg-surface px-2 py-1.5 text-body-md text-ink";
  const labelClass = "flex flex-col gap-1 text-body-sm text-ink-secondary";
  return (
    <SoftNavForm action={basePath} className="flex flex-col">
      {first(searchParams, "q") ? (
        <input type="hidden" name="q" value={first(searchParams, "q")} />
      ) : null}
      {first(searchParams, "sort") &&
      !(first(searchParams, "sort") === "relevance" && !first(searchParams, "q")) ? (
        <input type="hidden" name="sort" value={first(searchParams, "sort")} />
      ) : null}
      {REPEATABLE_FILTERS.filter(
        (name) => !APPLY_FACETS.includes(name as (typeof APPLY_FACETS)[number]),
      ).flatMap((name) =>
        values(searchParams, name).map((value) => (
          <input key={`${name}-${value}`} type="hidden" name={name} value={value} />
        )),
      )}

      <details className="refine-disclosure border-b border-rule">
        <summary className="flex min-h-11 cursor-pointer items-center justify-between py-2 text-body-sm font-medium text-ink">
          Access
        </summary>
        <fieldset className="flex flex-col gap-2 pb-3">
          <legend className="sr-only">Access</legend>
          {(
            [
              ["is_oa", "Open access only"],
              ["has_doi", "Has a DOI"],
              ["has_abstract", "Has an abstract"],
            ] as const
          ).map(([name, label]) => (
            <label
              key={name}
              className="flex min-h-11 items-center gap-2 text-body-sm text-ink-secondary"
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
      </details>

      <details className="refine-disclosure border-b border-rule">
        <summary className="flex min-h-11 cursor-pointer items-center justify-between py-2 text-body-sm font-medium text-ink">
          Publication year
        </summary>
        <div className="grid grid-cols-2 gap-2 pb-3">
          <YearRangeInputs
            key={`${first(searchParams, "year_min") || "any"}-${first(searchParams, "year_max") || "any"}`}
            startYear={yearStart}
            endYear={yearEnd}
            defaultFrom={first(searchParams, "year_min")}
            defaultTo={first(searchParams, "year_max")}
            inputClassName={inputClass}
            labelClassName={labelClass}
            allowEmpty
          />
        </div>
      </details>

      <FacetSelect
        name="type"
        label="Publication type"
        values={facets?.type ?? {}}
        current={first(searchParams, "type")}
      />
      <FacetSelect
        name="institution"
        label="Institution"
        values={facets?.sri_lankan_institutions ?? {}}
        current={first(searchParams, "institution")}
      />
      <FacetSelect
        name="journal"
        label="Journal"
        values={facets?.journal ?? {}}
        current={first(searchParams, "journal")}
      />

      <div className="mt-3 flex gap-2">
        <Button type="submit" variant="primary" size="sm">
          Apply
        </Button>
        <ResetFiltersButton href={basePath} />
      </div>
    </SoftNavForm>
  );
}

export function PublicationSort({
  searchParams,
  basePath = "/publications",
}: {
  searchParams: SearchParams;
  basePath?: string;
}) {
  const { navigate } = useFilterNavigation();
  const hasQuery = Boolean(first(searchParams, "q"));
  const current = first(searchParams, "sort");
  const value = current === "relevance" && !hasQuery ? "" : current;
  const options = SORT_OPTIONS.filter(
    (option) => option.value !== "relevance" || hasQuery,
  );

  return (
    <label className="flex items-center gap-2 text-body-sm text-ink-secondary">
      Sort
      <select
        aria-label="Sort publications"
        className="min-h-11 rounded border border-rule bg-surface px-2 text-body-sm text-ink"
        value={value}
        onChange={(event) => {
          const search = new URLSearchParams();
          for (const [key, raw] of Object.entries(searchParams)) {
            if (key === "page" || key === "sort") continue;
            for (const item of Array.isArray(raw) ? raw : raw ? [raw] : []) {
              if (item) search.append(key, item);
            }
          }
          if (event.target.value) search.set("sort", event.target.value);
          const qs = search.toString();
          navigate(qs ? `${basePath}?${qs}` : basePath);
        }}
      >
        <option value="">Default</option>
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
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

  const yearMin = first(searchParams, "year_min");
  const yearMax = first(searchParams, "year_max");
  if (yearMin && yearMax) {
    pills.push({
      key: "year-range",
      label: `Year: ${yearMin}–${yearMax}`,
      href: withoutParams(basePath, searchParams, ["year_min", "year_max"]),
    });
  } else {
    if (yearMin) {
      pills.push({
        key: `year_min:${yearMin}`,
        label: `Year: from ${yearMin}`,
        href: toggleFilterHref(basePath, searchParams, "year_min", yearMin),
      });
    }
    if (yearMax) {
      pills.push({
        key: `year_max:${yearMax}`,
        label: `Year: to ${yearMax}`,
        href: toggleFilterHref(basePath, searchParams, "year_max", yearMax),
      });
    }
  }

  const minCount = first(searchParams, "min_count");
  const maxCount = first(searchParams, "max_count");
  if (minCount && maxCount) {
    pills.push({
      key: `count:${minCount}:${maxCount}`,
      label:
        minCount === maxCount
          ? `Publications: ${minCount}`
          : `Publications: ${minCount}–${maxCount}`,
      href: withoutParams(basePath, searchParams, ["min_count", "max_count"]),
    });
  } else if (minCount) {
    pills.push({
      key: `min_count:${minCount}`,
      label: `Publications: ${minCount}+`,
      href: withoutParams(basePath, searchParams, ["min_count", "max_count"]),
    });
  } else if (maxCount) {
    pills.push({
      key: `max_count:${maxCount}`,
      label: `Publications: up to ${maxCount}`,
      href: withoutParams(basePath, searchParams, ["min_count", "max_count"]),
    });
  }

  for (const name of ["is_oa", "has_doi", "has_abstract"]) {
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

function withoutParams(
  basePath: string,
  searchParams: SearchParams,
  keys: string[],
): string {
  const search = new URLSearchParams();
  for (const [key, raw] of Object.entries(searchParams)) {
    if (key === "page" || keys.includes(key)) continue;
    for (const item of Array.isArray(raw) ? raw : raw ? [raw] : []) {
      if (item) search.append(key, item);
    }
  }
  const qs = search.toString();
  return qs ? `${basePath}?${qs}` : basePath;
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
