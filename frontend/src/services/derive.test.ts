import { describe, expect, it } from "vitest";

import {
  fieldShareInsight,
  networkInsight,
  publicationsForDisplay,
  trendInsight,
} from "./derive";
import type { PublicationSummary } from "@/types/api";

function publication(overrides: Partial<PublicationSummary>): PublicationSummary {
  return {
    publication_key: "source:test:1",
    title: "Sales forecasting using multivariate long short term memory network models",
    doi: "10.7287/peerj.preprints.27712v1",
    publication_year: 2019,
    publication_date: null,
    type: "preprint",
    authors: ["Suleka Helmini", "Nadeesh Jihan"],
    institutions: ["WSO2 (Sri Lanka)"],
    journal: null,
    publisher: null,
    citation_count: 0,
    reference_count: 0,
    is_oa: true,
    oa_status: "gold",
    primary_field: "Computer Science",
    primary_subfield: null,
    ai_classification_label: "AI",
    ai_classification_confidence: "HIGH",
    source_dataset: ["OpenAlex"],
    quality_flags: [],
    ...overrides,
  };
}

describe("publicationsForDisplay", () => {
  it("hides titleless records and collapses DOI version duplicates", () => {
    const rows = publicationsForDisplay([
      publication({
        publication_key: "doi:10.7287/peerj.preprints.27712v1",
        doi: "10.7287/peerj.preprints.27712v1",
        source_dataset: ["OpenAlex"],
      }),
      publication({
        publication_key: "doi:10.7287/peerj.preprints.27712",
        doi: "10.7287/peerj.preprints.27712",
        source_dataset: ["OpenAlex", "Crossref"],
      }),
      publication({
        publication_key: "doi:10.7287/peerj.preprints.27790/supp-1",
        title: null,
        doi: "10.7287/peerj.preprints.27790/supp-1",
      }),
    ]);

    expect(rows).toHaveLength(1);
    expect(rows[0].publication_key).toBe("doi:10.7287/peerj.preprints.27712");
    expect(rows[0].source_dataset).toEqual(["OpenAlex", "Crossref"]);
  });

  it("collapses same-title software records even when repository DOIs differ", () => {
    const rows = publicationsForDisplay([
      publication({
        publication_key: "doi:10.5281/zenodo.19508306",
        title: "kaushithamsilva/BACE: BACE - GECCO '26 Camera-Ready Release",
        doi: "10.5281/zenodo.19508306",
        journal: "Zenodo (CERN European Organization for Nuclear Research)",
      }),
      publication({
        publication_key: "doi:10.5281/zenodo.19508699",
        title: "kaushithamsilva/BACE: BACE - GECCO '26 Camera-Ready Release",
        doi: "10.5281/zenodo.19508699",
        journal: "Open MIND",
      }),
    ]);

    expect(rows).toHaveLength(1);
  });
});


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
