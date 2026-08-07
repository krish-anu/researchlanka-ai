import Link from "next/link";

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

/**
 * Structured controls as a plain GET form, so sorting and range filtering work
 * without client JavaScript. Repeatable filters chosen from the facet panel are
 * carried through as hidden inputs rather than being dropped on submit.
 */
export function FilterControls({
  searchParams,
  basePath = "/publications",
}: {
  searchParams: SearchParams;
  basePath?: string;
}) {
  const inputClass =
    "w-full rounded-md border border-hairline bg-page px-2 py-1.5 text-sm text-ink";

  return (
    <form method="get" action={basePath} className="panel flex flex-col gap-3 p-3">
      {/* Preserve free-text query and any facet selections across submits. */}
      {first(searchParams, "q") ? (
        <input type="hidden" name="q" value={first(searchParams, "q")} />
      ) : null}
      {REPEATABLE_FILTERS.flatMap((name) =>
        values(searchParams, name).map((value) => (
          <input key={`${name}-${value}`} type="hidden" name={name} value={value} />
        )),
      )}

      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-xs text-muted">
          Year from
          <input
            className={inputClass}
            type="number"
            name="year_min"
            inputMode="numeric"
            min={1900}
            max={2100}
            defaultValue={first(searchParams, "year_min")}
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted">
          Year to
          <input
            className={inputClass}
            type="number"
            name="year_max"
            inputMode="numeric"
            min={1900}
            max={2100}
            defaultValue={first(searchParams, "year_max")}
          />
        </label>
      </div>

      <label className="flex flex-col gap-1 text-xs text-muted">
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
        <legend className="pb-1 text-xs text-muted">Record properties</legend>
        {(
          [
            ["is_oa", "Open access only"],
            ["has_doi", "Has a DOI"],
            ["has_abstract", "Has an abstract"],
          ] as const
        ).map(([name, label]) => (
          <label key={name} className="flex items-center gap-2 text-sm text-ink-secondary">
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
        <button
          type="submit"
          className="flex-1 rounded-md border border-hairline bg-wash px-3 py-1.5 text-sm font-medium text-ink hover:bg-page"
        >
          Apply
        </button>
        <Link
          href={basePath}
          className="rounded-md border border-hairline px-3 py-1.5 text-sm text-ink-secondary hover:bg-wash"
        >
          Reset
        </Link>
      </div>
    </form>
  );
}

/** Removable pills for every active filter, so nothing filters invisibly. */
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
        label: `${titleCase(name)}: ${value}`,
        href: toggleFilterHref(basePath, searchParams, name, value),
      });
    }
  }

  for (const name of ["year_min", "year_max", "is_oa", "has_doi", "has_abstract"]) {
    const value = first(searchParams, name);
    if (!value) continue;
    pills.push({
      key: `${name}:${value}`,
      label: `${titleCase(name)}: ${value}`,
      href: toggleFilterHref(basePath, searchParams, name, value),
    });
  }

  if (pills.length === 0) return null;

  return (
    <ul className="flex flex-wrap gap-1.5" aria-label="Active filters">
      {pills.map((pill) => (
        <li key={pill.key}>
          <Link
            href={pill.href}
            className="inline-flex items-center gap-1.5 rounded-full border border-hairline bg-wash px-2.5 py-1 text-xs text-ink-secondary hover:text-ink"
          >
            {pill.label}
            <span aria-hidden className="text-muted">
              ✕
            </span>
            <span className="sr-only">Remove filter</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
