import { Suspense } from "react";
import { AnalyticsFilters } from "@/components/analytics/AnalyticsFilters";
import { NetworkPanel } from "@/components/analytics/ResearchPanels";
import { PageIntro } from "@/components/layout/PageIntro";
import { ActiveFilters } from "@/components/publications/FilterControls";
import { Skeleton } from "@/components/ui/Feedback";
import { getAnalyticsFields } from "@/services/api";
import { extractFilters, type SearchParams } from "@/services/filters";

export const metadata = { title: "AI research collaborations", description: "Explore institutional, researcher, and country collaboration networks across Sri Lanka’s accepted AI publications." };

export default async function CollaborationPage({ searchParams }: { searchParams: Promise<SearchParams> }) {
  const params = await searchParams;
  const filters = extractFilters(params);
  const scope = params.scope === "researcher" || params.scope === "country" ? params.scope : "institution";
  const positive = (value: string | string[] | undefined, fallback: number, max: number) => typeof value === "string" && /^\d+$/.test(value) ? Math.max(1, Math.min(max, Number(value))) : fallback;
  const limit = positive(params.limit, 120, 500), minWeight = positive(params.min_weight, 1, 10000);
  const fields = await getAnalyticsFields({ limit: 100 });
  return <div className="flex flex-col gap-6"><PageIntro title="Connected by discovery." description="Explore the partnerships bringing AI researchers, institutions, and countries together." />
    <AnalyticsFilters params={params} basePath="/collaboration" fields={fields.ok ? fields.value.data.map(f => f.label) : []} />
    <ActiveFilters searchParams={params} basePath="/collaboration" />
    <form method="get" action="/collaboration" className="analytics-filters panel p-4">
      {Object.entries(filters).flatMap(([key, value]) => (Array.isArray(value) ? value : value === undefined || value === null ? [] : [value]).map((v, i) => <input key={`${key}-${i}`} type="hidden" name={key} value={String(v)} />))}
      <label>Connections between<select name="scope" defaultValue={scope}><option value="institution">Institutions</option><option value="researcher">Researchers</option><option value="country">Countries</option></select></label>
      <label>Minimum shared publications<input name="min_weight" type="number" min="1" max="10000" defaultValue={minWeight} /></label>
      <label>Maximum nodes<input name="limit" type="number" min="1" max="500" defaultValue={limit} /></label>
      <button className="button button-primary" type="submit">Update network</button>
    </form>
    <Suspense fallback={<Skeleton className="h-[30rem]" />}><NetworkPanel filters={filters} scope={scope} limit={limit} minWeight={minWeight} /></Suspense>
  </div>;
}
