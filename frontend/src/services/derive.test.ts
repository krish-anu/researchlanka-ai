import { describe, expect, it } from "vitest";

import {
  fieldShareInsight,
  networkInsight,
  trendInsight,
} from "@/services/derive";

describe("trendInsight", () => {
  it("describes long-run change when multiple years exist", () => {
    const line = trendInsight([
      { key: 2016, publication_count: 100 },
      { key: 2020, publication_count: 150 },
      { key: 2024, publication_count: 200 },
    ]);
    expect(line).toMatch(/rose ~100%/);
    expect(line).toMatch(/2016/);
    expect(line).toMatch(/2024/);
  });

  it("appends OA share when provided", () => {
    const oa = new Map([["2024", 50]]);
    const line = trendInsight(
      [
        { key: 2023, publication_count: 80 },
        { key: 2024, publication_count: 100 },
      ],
      oa,
    );
    expect(line).toMatch(/OA share is 50\.0%/);
  });
});

describe("fieldShareInsight", () => {
  it("names the leading field", () => {
    expect(
      fieldShareInsight([
        { label: "Computer science", value: 40 },
        { label: "Medicine", value: 20 },
      ]),
    ).toBe("Computer science leads this view with 40 publications.");
  });
});

describe("networkInsight", () => {
  it("summarises a populated graph", () => {
    expect(networkInsight(12, 30, "institution")).toMatch(
      /12 institutions linked by 30/,
    );
  });

  it("handles an empty edge set", () => {
    expect(networkInsight(0, 0, "researcher")).toMatch(/No collaboration edges/);
  });
});
