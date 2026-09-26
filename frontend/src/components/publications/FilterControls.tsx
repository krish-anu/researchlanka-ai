import { getPublicationYearCoverage } from "@/services/api";
import type { SearchParams } from "@/services/filters";

import {
  ActiveFilters,
  FilterControlsForm,
} from "@/components/publications/FilterControlsForm";

export { ActiveFilters };

/**
 * Structured controls as a GET form. Soft-nav submit keeps results visible
 * while the next filter payload loads.
 */
export async function FilterControls({
  searchParams,
  basePath = "/publications",
}: {
  searchParams: SearchParams;
  basePath?: string;
}) {
  const coverage = await getPublicationYearCoverage();

  return (
    <FilterControlsForm
      searchParams={searchParams}
      basePath={basePath}
      yearStart={coverage?.start}
      yearEnd={coverage?.end}
    />
  );
}
