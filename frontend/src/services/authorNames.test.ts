import { describe, expect, it } from "vitest";

import { likelyListedName, nameMatch } from "@/services/authorNames";

describe("nameMatch", () => {
  // Kept in step with test_name_match in backend/tests/test_author_profiles.py.
  it.each([
    ["Chinthaka Jayatilake", "chinthaka jayatilake", "exact"],
    ["Senerath Mudalige Don Alexis Chinthaka Jayatilake", "Chinthaka Jayatilake", "initials"],
    ["Jayatilake, S.M.D.A.C.", "Chinthaka Jayatilake", "initials"],
    ["Perera A", "Anushka Perera", "initials"],
    ["Amaratunga, V", "Vinushi Amaratunga", "initials"],
    ["Anushka Perera", "Bimal Perera", "none"],
    ["Roshan Ragel", "Isuru Nawinne", "none"],
    ["", "Isuru Nawinne", "none"],
  ])("%s vs %s is %s", (listed, name, expected) => {
    expect(nameMatch(listed, name)).toBe(expected);
  });
});

describe("likelyListedName", () => {
  it("prefers an exact match over an initials match", () => {
    expect(
      likelyListedName(["C. Jayatilake", "Chinthaka Jayatilake", "Roshan Ragel"], ["Chinthaka Jayatilake"]),
    ).toBe("Chinthaka Jayatilake");
  });

  it("uses every name variant the applicant gave", () => {
    expect(likelyListedName(["Ragel, R", "Jayatilake, C"], ["Someone", "C Jayatilake"])).toBe(
      "Jayatilake, C",
    );
  });

  it("returns null when nobody on the list is plausibly the applicant", () => {
    expect(likelyListedName(["Roshan Ragel"], ["Chinthaka Jayatilake"])).toBeNull();
  });
});
