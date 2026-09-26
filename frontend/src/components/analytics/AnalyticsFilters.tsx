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
}: {
  params: SearchParams;
  fields?: string[];
  basePath?: string;
  defaultFrom?: number;
  defaultTo?: number;
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
    />
  );
}
