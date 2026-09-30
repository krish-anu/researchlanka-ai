import type { ReactNode } from "react";

import type { SearchParams } from "@/services/filters";
import {
  AnalyticsFiltersForm,
  type FilterChoice,
} from "@/components/analytics/AnalyticsFiltersForm";
import type { QueryParams } from "@/services/api";
import type { RankingEntry } from "@/types/api";

export function toFilterChoices(rows: RankingEntry[] | undefined): FilterChoice[] {
  return (rows ?? [])
    .filter((row) => row.publication_count > 0 && row.label)
    .map((row) => ({ label: row.label, count: row.publication_count }));
}

export function withoutQueryKey(params: QueryParams, key: string): QueryParams {
  if (!(key in params)) return params;
  const next = { ...params };
  delete next[key];
  return next;
}
import { getPublicationYearCoverage } from "@/services/api";

/** GET controls retain unrelated filters, making links and exports reproducible. */
export async function AnalyticsFilters({
  params,
  fields = [],
  basePath = "/",
  defaultFrom,
  defaultTo,
  title,
  summaryLabel,
  extraControls,
  omitParamKeys,
  applyLabel,
  institutions,
  yearPhrase,
  fromLabel,
  toLabel,
  showMinCount,
  layout = "card",
  deferUntilField = false,
}: {
  params: SearchParams;
  fields?: Array<string | FilterChoice>;
  basePath?: string;
  defaultFrom?: number;
  defaultTo?: number;
  title?: string;
  summaryLabel?: string;
  extraControls?: ReactNode;
  omitParamKeys?: string[];
  applyLabel?: string;
  institutions?: Array<string | FilterChoice>;
  yearPhrase?: string;
  fromLabel?: string;
  toLabel?: string;
  showMinCount?: boolean;
  /** `refine` stacks collapsed sections for a narrow directory sidebar. */
  layout?: "card" | "refine";
  deferUntilField?: boolean;
}) {
  const coverage = await getPublicationYearCoverage();

  return (
    <AnalyticsFiltersForm
      params={params}
      fields={fields}
      basePath={basePath}
      defaultFrom={defaultFrom}
      defaultTo={defaultTo}
      yearStart={coverage?.start}
      yearEnd={coverage?.end}
      title={title}
      summaryLabel={summaryLabel}
      extraControls={extraControls}
      omitParamKeys={omitParamKeys}
      applyLabel={applyLabel}
      institutions={institutions}
      yearPhrase={yearPhrase}
      fromLabel={fromLabel}
      toLabel={toLabel}
      showMinCount={showMinCount}
      layout={layout}
      deferUntilField={deferUntilField}
    />
  );
}
