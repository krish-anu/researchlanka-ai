import { REPEATABLE_FILTERS, type SearchParams } from "@/services/filters";
import { titleCase } from "@/services/format";

function first(
  params: SearchParams,
  name: string,
): string | undefined {
  const value = params[name];
  if (Array.isArray(value)) return value[0];
  return typeof value === "string" ? value : undefined;
}

function values(params: SearchParams, name: string): string[] {
  const value = params[name];
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string");
  }
  return typeof value === "string" ? [value] : [];
}

const FILTER_KEY_LABELS: Record<string, string> = {
  type: "Type",
  institution: "Institution",
  country: "Country",
  domain: "Domain",
  field: "Field",
  researcher: "Researcher",
  subfield: "Subfield",
  topic: "Topic",
  nmf_topic: "Topic model",
  nmf_topic_id: "Topic id",
  journal: "Journal",
  source_dataset: "Source",
  quality_flag: "Quality",
  scope: "Connections",
  min_weight: "Min shared pubs",
  limit: "Max nodes",
};

const SCOPE_VALUE_LABELS: Record<string, string> = {
  institution: "Institutions",
  researcher: "Researchers",
  country: "Countries",
};

function filterPillLabel(name: string, value: string): string {
  if (name === "is_oa") {
    return value === "true" ? "Open access" : "Not open access";
  }
  if (name === "has_doi") {
    return value === "true" ? "Has a DOI" : "Missing DOI";
  }
  if (name === "has_abstract") {
    return value === "true" ? "Has an abstract" : "Missing abstract";
  }
  if (name === "year_min") return `From ${value}`;
  if (name === "year_max") return `To ${value}`;
  if (name === "scope") {
    return `Connections: ${SCOPE_VALUE_LABELS[value] ?? value}`;
  }
  const key =
    FILTER_KEY_LABELS[name] ?? titleCase(name.replaceAll("_", " "));
  return `${key}: ${value}`;
}

/** Comma-separated filter summary for print / cite headers. */
export function summarizeActiveFilters(searchParams: SearchParams): string | null {
  const parts: string[] = [];

  for (const name of REPEATABLE_FILTERS) {
    for (const value of values(searchParams, name)) {
      parts.push(filterPillLabel(name, value));
    }
  }
  for (const name of [
    "year_min",
    "year_max",
    "is_oa",
    "has_doi",
    "has_abstract",
    "scope",
    "min_weight",
    "limit",
  ]) {
    const value = first(searchParams, name);
    if (!value) continue;
    parts.push(filterPillLabel(name, value));
  }

  return parts.length ? parts.join("; ") : null;
}
