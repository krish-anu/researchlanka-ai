import { describe, expect, it } from "vitest";
import { analyticsExportUrl, exportUrl } from "./api";

describe("browser exports", () => {
  it("uses the same-origin API route and preserves repeated filters and access flags", () => {
    const url = new URL(exportUrl("publications.csv", { institution: ["University of Colombo", "University of Moratuwa"], year_min: 2021, is_oa: true }), "https://research.example");
    expect(url.origin).toBe("https://research.example");
    expect(url.pathname).toBe("/api/v1/exports/publications.csv");
    expect(url.searchParams.getAll("institution")).toEqual(["University of Colombo", "University of Moratuwa"]);
    expect(url.searchParams.get("year_min")).toBe("2021");
    expect(url.searchParams.get("is_oa")).toBe("true");
  });
  it("keeps the chart's selection and grouping in the analytics CSV", () => {
    expect(analyticsExportUrl("trends", { field: ["Computer Science"], group_by: "year", year_max: 2025 })).toBe("/api/v1/exports/analytics/trends.csv?field=Computer+Science&group_by=year&year_max=2025");
  });
});
