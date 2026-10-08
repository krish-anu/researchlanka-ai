/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthorRowsEditor,
  submitterRow,
  type SubmitterIdentity,
} from "@/components/authors/AuthorRowsEditor";
import type { SubmissionAuthor } from "@/types/authors";

const ME: SubmitterIdentity = {
  slug: "roshan-ragel",
  display_name: "Roshan Ragel",
  names: ["Roshan Ragel", "Roshan G. Ragel"],
  institution: "University of Peradeniya",
  affiliations: [
    { institution: "University of Peradeniya", department: "", position_title: "", start_year: 2022, end_year: null },
    { institution: "University of Moratuwa", department: "", position_title: "", start_year: 2010, end_year: 2021 },
  ],
};

let latest: SubmissionAuthor[] = [];

function Harness({ year }: { year: number | null }) {
  const [rows, setRows] = useState<SubmissionAuthor[]>(() => [submitterRow(ME, year)]);
  latest = rows;
  return <AuthorRowsEditor rows={rows} onChange={setRows} me={ME} year={year} error={null} />;
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const data = url.includes("/lookup/authors")
        ? {
            names: [{ name: "Isuru Nawinne", publication_count: 2, year_min: 2023, year_max: 2026, profile: null }],
            profiles: [],
          }
        : [];
      return new Response(JSON.stringify({ data }), { status: 200 });
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AuthorRowsEditor", () => {
  it("starts with the submitter, filed under their institution in the paper's year", () => {
    render(<Harness year={2019} />);

    expect(latest).toHaveLength(1);
    expect(latest[0]).toMatchObject({
      name: "Roshan Ragel",
      institution: "University of Moratuwa",
      profile_slug: "roshan-ragel",
      is_submitter: true,
    });
    expect(screen.getByText(/Your verified profile/)).toBeTruthy();
  });

  it("adds co-authors, links a printed name and keeps every row", async () => {
    render(<Harness year={2024} />);

    fireEvent.click(screen.getByRole("button", { name: "Add an author" }));
    fireEvent.change(screen.getByLabelText("Name as printed on the paper", { selector: "#author-1-name" }), {
      target: { value: "Nawinne" },
    });
    fireEvent.click(await screen.findByRole("button", { name: /Isuru Nawinne/ }));
    fireEvent.change(document.getElementById("author-1-institution")!, { target: { value: "University of Peradeniya" } });

    fireEvent.click(screen.getByRole("button", { name: "Add an author" }));
    fireEvent.change(document.getElementById("author-2-name")!, { target: { value: "Jane Doe" } });
    fireEvent.change(document.getElementById("author-2-institution")!, { target: { value: "University of Oxford" } });
    fireEvent.change(screen.getByLabelText("Author 3 country code"), { target: { value: "gb" } });

    expect(latest.map((row) => [row.name, row.institution, row.country_code, row.is_submitter])).toEqual([
      ["Roshan Ragel", "University of Peradeniya", null, true],
      ["Isuru Nawinne", "University of Peradeniya", null, false],
      ["Jane Doe", "University of Oxford", "GB", false],
    ]);

    // Removing the middle author keeps the others intact and in order.
    fireEvent.click(screen.getByRole("button", { name: "Remove author 2" }));
    expect(latest.map((row) => row.name)).toEqual(["Roshan Ragel", "Jane Doe"]);
  });

  it("allows only one row to be the submitter", () => {
    render(<Harness year={2024} />);
    fireEvent.click(screen.getByRole("button", { name: "Add an author" }));
    fireEvent.change(document.getElementById("author-1-name")!, { target: { value: "Roshan G. Ragel" } });

    const second = screen.getAllByRole("listitem")[1];
    fireEvent.click(within(second).getByLabelText("This is me"));

    expect(latest.map((row) => [row.name, row.is_submitter, row.profile_slug])).toEqual([
      ["Roshan Ragel", false, null],
      ["Roshan G. Ragel", true, "roshan-ragel"],
    ]);
  });

  it("drops a profile link when the linked name is retyped", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            data: {
              names: [],
              profiles: [{ slug: "isuru", display_name: "Isuru Nawinne", institution: "University of Peradeniya", name_variants: [] }],
            },
          }),
          { status: 200 },
        ),
      ),
    );
    render(<Harness year={2024} />);
    fireEvent.click(screen.getByRole("button", { name: "Add an author" }));
    fireEvent.change(document.getElementById("author-1-name")!, { target: { value: "Isuru Nawinne" } });
    fireEvent.click(await screen.findByRole("button", { name: /verified profile/ }));
    expect(latest[1].profile_slug).toBe("isuru");

    fireEvent.change(document.getElementById("author-1-name")!, { target: { value: "Someone Else" } });
    expect(latest[1].profile_slug).toBeNull();
  });
});
