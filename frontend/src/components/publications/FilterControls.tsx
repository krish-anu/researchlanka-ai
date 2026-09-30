import { getPublicationYearCoverage } from "@/services/api";
import type { SearchParams } from "@/services/filters";
import type { Facets } from "@/types/api";

import {
  ActiveFilters,
  FilterControlsForm,
  PublicationSort,
} from "@/components/publications/FilterControlsForm";

export { ActiveFilters, PublicationSort };

/**
 * Structured controls as a GET form. Soft-nav submit keeps results visible
 * while the next filter payload loads.
 */
export async function FilterControls({
  searchParams,
  basePath = "/publications",
  facets,
}: {
  searchParams: SearchParams;
  basePath?: string;
  facets?: Facets;
}) {
  const coverage = await getPublicationYearCoverage();

  return (
    <FilterControlsForm
      searchParams={searchParams}
      basePath={basePath}
      yearStart={coverage?.start}
      yearEnd={coverage?.end}
      facets={facets}
    />
  );
}
