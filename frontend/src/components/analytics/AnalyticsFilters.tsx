import type { ReactNode } from "react";

import type { SearchParams } from "@/services/filters";
import { AnalyticsFiltersForm } from "@/components/analytics/AnalyticsFiltersForm";
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
}: {
  params: SearchParams;
  fields?: string[];
  basePath?: string;
  defaultFrom?: number;
  defaultTo?: number;
  title?: string;
  summaryLabel?: string;
  extraControls?: ReactNode;
  omitParamKeys?: string[];
  applyLabel?: string;
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
    />
  );
}
