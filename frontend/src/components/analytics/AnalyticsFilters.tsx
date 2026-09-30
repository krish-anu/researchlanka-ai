import Link from "next/link";
import type { SearchParams } from "@/services/filters";

/** GET controls retain unrelated filters, making links and exports reproducible. */
export function AnalyticsFilters({ params, fields = [], basePath = "/", defaultFrom, defaultTo }: { params: SearchParams; fields?: string[]; basePath?: string; defaultFrom?: number; defaultTo?: number }) {
  const first = (key: string) => { const value = params[key]; return Array.isArray(value) ? value[0] : value; };
  const selected = first("field") ?? "";
  const options = [...new Set([...fields, ...(selected ? [selected] : [])])];
  return <form method="get" action={basePath} className="analytics-filters">
    {Object.entries(params).filter(([key]) => !["year_min", "year_max", "field", "page", "fields_page", "topics_page"].includes(key)).flatMap(([key, value]) => (Array.isArray(value) ? value : value ? [value] : []).map((v, i) => <input type="hidden" name={key} value={v} key={`${key}-${i}`} />))}
    <label>Year from<input type="number" min="1900" max="2100" name="year_min" defaultValue={first("year_min") ?? defaultFrom} /></label>
    <label>Year to<input type="number" min="1900" max="2100" name="year_max" defaultValue={first("year_max") ?? defaultTo} /></label>
    <label>Research field<select name="field" defaultValue={selected}><option value="">All fields within AI publications</option>{options.map(field => <option key={field}>{field}</option>)}</select></label>
    {Array.isArray(params.field) ? params.field.slice(1).map((field, i) => <input type="hidden" key={`field-${i}`} name="field" value={field} />) : null}
    <button type="submit" className="button button-primary">Apply filters</button><Link href={basePath} className="button">Reset</Link>
  </form>;
}
