import { describe, expect, it } from "vitest";

import { institutionForYear, periodLabel } from "@/services/affiliations";
import type { Affiliation } from "@/types/authors";

const history: Affiliation[] = [
  { institution: "University of Peradeniya", department: "", position_title: "", start_year: 2021, end_year: null },
  { institution: "University of Moratuwa", department: "", position_title: "", start_year: 2012, end_year: 2020 },
];

describe("institutionForYear", () => {
  it("files a paper under the institution of its year", () => {
    expect(institutionForYear(history, 2018, "Profile Institute")).toBe("University of Moratuwa");
    expect(institutionForYear(history, 2023, "Profile Institute")).toBe("University of Peradeniya");
  });

  it("falls back to the current position, then the profile", () => {
    expect(institutionForYear(history, 2005, "Profile Institute")).toBe("University of Peradeniya");
    expect(institutionForYear(history, null, "Profile Institute")).toBe("University of Peradeniya");
    expect(institutionForYear([], 2018, "Profile Institute")).toBe("Profile Institute");
  });
});

describe("periodLabel", () => {
  it.each([
    [{ start_year: 2012, end_year: 2020 }, "2012–2020"],
    [{ start_year: 2021, end_year: null }, "2021–present"],
    [{ start_year: 2019, end_year: 2019 }, "2019"],
    [{ start_year: null, end_year: 2015 }, "until 2015"],
    [{ start_year: null, end_year: null }, ""],
  ])("%o reads as %s", (period, expected) => {
    expect(periodLabel(period)).toBe(expected);
  });
});
