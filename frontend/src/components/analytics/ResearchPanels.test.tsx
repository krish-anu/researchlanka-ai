import { describe, expect, it, vi } from "vitest";
const { trends } = vi.hoisted(() => ({ trends: vi.fn() }));
vi.mock("@/services/api", async importOriginal => ({ ...await importOriginal<typeof import("@/services/api")>(), getAnalyticsTrends: trends }));
import { TrendPanel, InstitutionAccessibilityPanel } from "./ResearchPanels";
import { InstitutionScatterChart } from "@/components/charts/InstitutionScatterChart";
import { TrendLineChart } from "@/components/charts/TrendLineChart";
import { Children, isValidElement } from "react";

const data = [{ key: 2025, publication_count: 10, citation_total: 0 }];
function childProps(element: Awaited<ReturnType<typeof TrendPanel>>, type: unknown) {
  const child = Children.toArray(element.props.children).find(child => isValidElement(child) && child.type === type);
  if (!isValidElement(child)) throw new Error("Expected chart child");
  return child.props as Record<string, unknown>;
}

describe("open access stays within the selected AI corpus", () => {
  it("does not replace a non-open filter with the opposite population in annual comparisons", async () => {
    trends.mockReset().mockResolvedValue({ ok: true, value: { data } });
    const panel = await TrendPanel({ filters: { is_oa: "false", year_min: 2025 } });
    expect(trends).toHaveBeenCalledTimes(1);
    expect(trends.mock.calls[0][0]).toMatchObject({ is_oa: "false", year_min: 2025 });
    expect(childProps(panel, TrendLineChart).secondary).toEqual({ label: "Open access", points: [{ key: 2025, value: 0 }] });
  });
  it("keeps institutional open-access shares at zero for a non-open selection", async () => {
    trends.mockReset();
    const panel = await InstitutionAccessibilityPanel({ filters: { is_oa: false }, entries: [{ key: "colombo", label: "Colombo", publication_count: 10, citation_total: 0 }] });
    expect(trends).not.toHaveBeenCalled();
    expect(childProps(panel, InstitutionScatterChart).points).toEqual([{ label: "Colombo", publications: 10, openAccessShare: 0 }]);
  });
});
