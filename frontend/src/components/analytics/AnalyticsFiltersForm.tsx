"use client";

import { Button } from "@/components/ui/Button";
import { YearRangeInputs } from "@/components/ui/YearRangeInputs";
import {
  SoftNavForm,
  useFilterNavigation,
} from "@/components/navigation/FilterNavigation";
import type { SearchParams } from "@/services/filters";

function firstValue(params: SearchParams, key: string): string {
  const value = params[key];
  if (Array.isArray(value)) return value[0] ?? "";
  return value ?? "";
}

function ResetFiltersButton({ href }: { href: string }) {
  const { navigate } = useFilterNavigation();
  return (
    <Button type="button" variant="ghost" onClick={() => navigate(href)}>
      Reset
    </Button>
  );
}

/**
 * Instant-apply analytics filter bar: changing year or field reloads results.
 * Soft-navigates so current charts stay visible while the next payload loads.
 */
export function AnalyticsFiltersForm({
  params,
  fields,
  basePath,
  defaultFrom,
  defaultTo,
  yearStart,
  yearEnd,
}: {
  params: SearchParams;
  fields: string[];
  basePath: string;
  defaultFrom?: number;
  defaultTo?: number;
  yearStart?: number;
  yearEnd?: number;
}) {
  const selected = firstValue(params, "field");
  const options = [...new Set([...fields, ...(selected ? [selected] : [])])];
  const prefilledYears = defaultFrom != null || defaultTo != null;

  return (
    <SoftNavForm action={basePath} className="analytics-filters">
      {Object.entries(params)
        .filter(
          ([key]) =>
            !["year_min", "year_max", "field", "page", "fields_page", "topics_page"].includes(
              key,
            ),
        )
        .flatMap(([key, value]) =>
          (Array.isArray(value) ? value : value ? [value] : []).map((item, index) => (
            <input type="hidden" name={key} value={item} key={`${key}-${index}`} />
          )),
        )}

      <YearRangeInputs
        startYear={yearStart}
        endYear={yearEnd}
        defaultFrom={firstValue(params, "year_min") || defaultFrom}
        defaultTo={firstValue(params, "year_max") || defaultTo}
        allowEmpty={!prefilledYears}
        autoSubmit
      />

      <label>
        Research field
        <select
          name="field"
          defaultValue={selected}
          onChange={(event) => event.currentTarget.form?.requestSubmit()}
        >
          <option value="">All fields within AI publications</option>
          {options.map((field) => (
            <option key={field} value={field}>
              {field}
            </option>
          ))}
        </select>
      </label>

      {Array.isArray(params.field)
        ? params.field.slice(1).map((field, index) => (
            <input type="hidden" key={`field-${index}`} name="field" value={field} />
          ))
        : null}

      <div className="flex items-center gap-2">
        <ResetFiltersButton href={basePath} />
      </div>
    </SoftNavForm>
  );
}
