import { describe, expect, it } from "vitest";

import {
  formatAuthorList,
  formatCompact,
  formatDate,
  formatDecimal,
  formatNumber,
  formatPercent,
  formatRatioAsPercent,
  formatYearRange,
  titleCase,
  truncate,
} from "@/services/format";

/**
 * These run on every page, over API data that is frequently null. The point of
 * the suite is the missing-value contract: a figure the API could not supply
 * must render as an em dash, never as "0", "NaN" or "null" — each of which a
 * reader would take as a measurement.
 */
describe("missing values never render as a number", () => {
  const formatters: [string, (value: null | undefined) => string][] = [
    ["formatNumber", formatNumber],
    ["formatCompact", formatCompact],
    ["formatDecimal", formatDecimal],
    ["formatRatioAsPercent", formatRatioAsPercent],
    ["formatPercent", formatPercent],
  ];

  it.each(formatters)("%s renders null and undefined as an em dash", (_name, format) => {
    expect(format(null)).toBe("—");
    expect(format(undefined)).toBe("—");
  });

  it("rejects NaN and Infinity, which arithmetic on partial data produces", () => {
    expect(formatNumber(Number.NaN)).toBe("—");
    expect(formatNumber(Number.POSITIVE_INFINITY)).toBe("—");
    expect(formatDecimal(Number.NaN)).toBe("—");
    expect(formatRatioAsPercent(Number.NaN)).toBe("—");
  });

  it("still renders a genuine zero, which is a measurement", () => {
    expect(formatNumber(0)).toBe("0");
    expect(formatPercent(0)).toBe("0.0%");
    expect(formatDecimal(0)).toBe("0.00");
  });
});

describe("formatNumber", () => {
  it("groups thousands", () => {
    expect(formatNumber(1234567)).toBe("1,234,567");
  });

  it("keeps negatives signed", () => {
    expect(formatNumber(-42)).toBe("-42");
  });
});

describe("formatCompact", () => {
  it("stays exact below the 10,000 threshold, where digits are still readable", () => {
    expect(formatCompact(9999)).toBe("9,999");
  });

  it("abbreviates at and above the threshold", () => {
    expect(formatCompact(10_000)).toBe("10K");
    expect(formatCompact(1_500_000)).toBe("1.5M");
  });

  it("applies the threshold to magnitude, so large negatives abbreviate too", () => {
    expect(formatCompact(-12_000)).toBe("-12K");
  });
});

describe("percentage formatters are not interchangeable", () => {
  // The API returns 0..1 for coverage/share fields but 0..100 from
  // /analytics/data-quality. Swapping the two would misreport by 100x, so the
  // distinction is worth pinning.
  it("formatRatioAsPercent scales a 0..1 ratio", () => {
    expect(formatRatioAsPercent(0.425)).toBe("42.5%");
    expect(formatRatioAsPercent(1)).toBe("100.0%");
  });

  it("formatPercent passes an already-scaled percentage through", () => {
    expect(formatPercent(42.5)).toBe("42.5%");
    expect(formatPercent(100)).toBe("100.0%");
  });

  it("honours a requested precision", () => {
    expect(formatRatioAsPercent(0.12345, 2)).toBe("12.35%");
    expect(formatPercent(12.345, 0)).toBe("12%");
  });
});

describe("formatDate", () => {
  it("renders an ISO timestamp in the platform's date style", () => {
    expect(formatDate("2026-03-15T10:30:00Z")).toBe("15 Mar 2026");
  });

  it("renders a bare ISO date", () => {
    expect(formatDate("2026-03-15")).toBe("15 Mar 2026");
  });

  it("returns an em dash for a missing date", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("")).toBe("—");
  });

  it("passes an unparseable value through rather than showing Invalid Date", () => {
    // Source records carry partial dates like "2024" or free text. Echoing the
    // original is more use to a reader than the browser's error string.
    expect(formatDate("not a date")).toBe("not a date");
  });
});

describe("formatYearRange", () => {
  it("joins two distinct years", () => {
    expect(formatYearRange(1998, 2025)).toContain("1998");
    expect(formatYearRange(1998, 2025)).toContain("2025");
  });

  it("returns an em dash when the lower bound is missing", () => {
    expect(formatYearRange(null, 2025)).toBe("—");
  });
});

describe("truncate", () => {
  it("leaves a string within the limit untouched", () => {
    expect(truncate("short title", 40)).toBe("short title");
  });

  it("never exceeds the limit, including the ellipsis", () => {
    const result = truncate("a".repeat(80), 40);
    expect(result.length).toBeLessThanOrEqual(40);
    expect(result.endsWith("…")).toBe(true);
  });
});

describe("titleCase", () => {
  it("capitalises each word", () => {
    expect(titleCase("journal article")).toBe("Journal Article");
  });
});

describe("formatAuthorList", () => {
  it("lists every author when under the cap", () => {
    expect(formatAuthorList(["Perera, A.", "Silva, R."])).toContain("Perera, A.");
    expect(formatAuthorList(["Perera, A.", "Silva, R."])).toContain("Silva, R.");
  });

  it("summarises the tail beyond the cap rather than truncating mid-list", () => {
    const authors = Array.from({ length: 12 }, (_, i) => `Author ${i}`);
    const result = formatAuthorList(authors, 3);

    expect(result).toContain("Author 0");
    expect(result).not.toContain("Author 11");
    expect(result).toMatch(/9/); // the count of those not shown
  });

  it("handles an empty author list", () => {
    expect(typeof formatAuthorList([])).toBe("string");
  });
});
