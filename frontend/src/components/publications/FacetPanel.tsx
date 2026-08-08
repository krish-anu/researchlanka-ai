import Link from "next/link";

import { toggleFilterHref, type SearchParams } from "@/services/filters";
import { formatNumber, titleCase } from "@/services/format";
import type { Facets } from "@/types/api";

/**
 * Facet name -> the query parameter it filters on. The API returns facets keyed
 * by column, which is not always the filter name (`sri_lankan_institutions`
 * facets the `institution` filter).
 */
const FACET_TO_FILTER: Record<string, { param: string; label: string }> = {
  publication_year: { param: "year_min", label: "Year" },
  type: { param: "type", label: "Publication type" },
  primary_field: { param: "field", label: "Field" },
  primary_subfield: { param: "subfield", label: "Subfield" },
  topics: { param: "topic", label: "Topic" },
  sri_lankan_institutions: { param: "institution", label: "Institution" },
  countries: { param: "country", label: "Country" },
  journal: { param: "journal", label: "Journal" },
  source_dataset: { param: "source_dataset", label: "Source" },
  quality_flags: { param: "quality_flag", label: "Data quality" },
};

/** Year facets drive a range filter, so they are rendered separately. */
const FACET_ORDER = [
  "type",
  "primary_field",
  "primary_subfield",
  "topics",
  "sri_lankan_institutions",
  "countries",
  "journal",
  "source_dataset",
  "quality_flags",
];

function FacetGroup({
  facetName,
  values,
  searchParams,
  basePath,
}: {
  facetName: string;
  values: Record<string, number>;
  searchParams: SearchParams;
  basePath: string;
}) {
  const config = FACET_TO_FILTER[facetName];
  if (!config) return null;

  const entries = Object.entries(values)
    .filter(([value]) => value !== "")
    .slice(0, 12);
  if (entries.length === 0) return null;

  const active = new Set(
    (Array.isArray(searchParams[config.param])
      ? (searchParams[config.param] as string[])
      : searchParams[config.param]
        ? [searchParams[config.param] as string]
        : []) ?? [],
  );

  return (
    <details className="border-b border-rule pb-2 last:border-0" open>
      <summary className="label-caps cursor-pointer py-3 text-ink">
        {config.label}
      </summary>
      <ul className="flex flex-col gap-0.5 pb-1">
        {entries.map(([value, count]) => {
          const isActive = active.has(value);
          return (
            <li key={value}>
              <Link
                href={toggleFilterHref(basePath, searchParams, config.param, value)}
                className={`flex items-start justify-between gap-2 rounded px-2 py-1.5 text-body-sm hover:bg-wash ${
                  isActive
                    ? "bg-primary-muted font-medium text-ink"
                    : "text-ink-secondary"
                }`}
              >
                <span className="flex min-w-0 items-start gap-1.5">
                  <span aria-hidden className="mt-0.5 shrink-0">
                    {isActive ? "✓" : "·"}
                  </span>
                  <span className="break-words">
                    {facetName === "quality_flags" ? titleCase(value) : value}
                  </span>
                </span>
                <span className="data-mono mt-1 shrink-0 text-muted">
                  {formatNumber(count)}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

/**
 * Structured filters alongside search results. Counts respect the active
 * filter context, so a value showing 0 remaining matches simply disappears.
 */
export function FacetPanel({
  facets,
  searchParams,
  basePath = "/publications",
}: {
  facets: Facets;
  searchParams: SearchParams;
  basePath?: string;
}) {
  const groups = FACET_ORDER.filter(
    (name) => facets[name] && Object.keys(facets[name]).length > 0,
  );

  if (groups.length === 0) {
    return (
      <p className="p-3 text-body-sm text-muted">
        No facet counts are available for this result set.
      </p>
    );
  }

  return (
    <div className="panel p-4">
      <h2 className="label-caps mb-2 text-muted">Refine</h2>
      {groups.map((name) => (
        <FacetGroup
          key={name}
          facetName={name}
          values={facets[name]}
          searchParams={searchParams}
          basePath={basePath}
        />
      ))}
    </div>
  );
}
