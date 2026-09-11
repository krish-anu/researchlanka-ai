import { describe, expect, it } from "vitest";

import {
  decodeKeySegments,
  institutionHref,
  publicationHref,
  publicationSearchHref,
  researcherHref,
  topicHref,
} from "@/services/links";

/**
 * Publication keys look like `doi:10.1000/example` and contain slashes, so
 * publication routes are catch-all and each segment is encoded separately —
 * percent-encoding the slash would collapse the segments and break the route.
 * These tests pin that round trip, because the encode and decode halves live in
 * different files and only agree by convention.
 */
describe("publicationHref", () => {
  it("keeps the slash inside a DOI as a path separator", () => {
    expect(publicationHref("doi:10.1000/example")).toBe(
      "/publications/doi%3A10.1000/example",
    );
  });

  it("encodes characters that would otherwise change the URL's meaning", () => {
    // A question mark would start a query string and silently truncate the key.
    expect(publicationHref("doi:10.1000/a?b")).toBe(
      "/publications/doi%3A10.1000/a%3Fb",
    );
    expect(publicationHref("doi:10.1000/a#b")).toBe(
      "/publications/doi%3A10.1000/a%23b",
    );
  });

  it("encodes spaces", () => {
    expect(publicationHref("key with spaces")).toBe("/publications/key%20with%20spaces");
  });
});

describe("key round trip", () => {
  const keys = [
    "doi:10.1000/example",
    "doi:10.1016/j.envdev.2023.100842",
    "doi:10.1000/a?b#c",
    "doi:10.1000/nested/path/segments",
    "openalex:W123456",
    "key with spaces",
    "unicode:ආයුබෝවන්",
  ];

  it.each(keys)("survives encode then decode: %s", (key) => {
    const path = publicationHref(key).replace("/publications/", "");
    expect(decodeKeySegments(path.split("/"))).toBe(key);
  });
});

describe("decodeKeySegments", () => {
  it("rejoins catch-all segments into the original key", () => {
    expect(decodeKeySegments(["doi%3A10.1000", "example"])).toBe("doi:10.1000/example");
  });

  it("returns an empty string for a missing route parameter", () => {
    expect(decodeKeySegments(undefined)).toBe("");
    expect(decodeKeySegments([])).toBe("");
  });
});

/**
 * Profile routes carry the human label, not a slug. The backend resolves them
 * with `column ILIKE %value%` against raw stored text, so a slugified route
 * would never match — a subtlety worth a test, since the two look
 * interchangeable at a call site.
 */
describe("profile routes carry labels, not slugs", () => {
  it("keeps institution names human-readable and spaced", () => {
    expect(institutionHref("University of Colombo")).toBe(
      "/institutions/University%20of%20Colombo",
    );
  });

  it("does not lowercase or hyphenate", () => {
    const href = institutionHref("University of Colombo");
    expect(href).not.toContain("university-of-colombo");
  });

  it("encodes a comma inside an institution name rather than splitting on it", () => {
    // "Eastern University, Sri Lanka" is one institution.
    expect(institutionHref("Eastern University, Sri Lanka")).toBe(
      "/institutions/Eastern%20University%2C%20Sri%20Lanka",
    );
  });

  it("handles researcher and topic labels the same way", () => {
    expect(researcherHref("Perera, A.")).toBe("/researchers/Perera%2C%20A.");
    expect(topicHref("Climate change")).toBe("/topics/Climate%20change");
  });
});

describe("publicationSearchHref", () => {
  it("returns the bare route when no filters are supplied", () => {
    expect(publicationSearchHref({})).toBe("/publications");
  });

  it("builds a query string from the supplied filters", () => {
    const href = publicationSearchHref({ year_min: 2020, type: "journal-article" });

    expect(href.startsWith("/publications?")).toBe(true);
    expect(href).toContain("year_min=2020");
    expect(href).toContain("type=journal-article");
  });

  it("drops undefined and empty values instead of sending blank filters", () => {
    // A blank filter is not the same as no filter: the API would treat it as a
    // real constraint and return nothing.
    expect(publicationSearchHref({ q: undefined, type: "" })).toBe("/publications");
  });

  it("keeps a zero, which is a real filter value", () => {
    expect(publicationSearchHref({ min_citations: 0 })).toContain("min_citations=0");
  });

  it("encodes values containing spaces and ampersands", () => {
    const href = publicationSearchHref({ institution: "Colombo & Kelaniya" });
    expect(href).toContain("institution=Colombo+%26+Kelaniya");
  });
});
