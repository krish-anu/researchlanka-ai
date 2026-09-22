/** @vitest-environment jsdom */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ChartPanel } from "./ChartPanel";
import { TableDisclosure } from "./DataTable";
import { ViewSwitcher } from "./ViewSwitcher";

afterEach(cleanup);
describe("chart and directory views", () => {
  it("opens the accessible table when switching away from the chart and retains export actions", () => {
    render(<ChartPanel title="AI output" action={<a href="/export">Download CSV</a>} table={<TableDisclosure><table><tbody><tr><td>1030 publications</td></tr></tbody></table></TableDisclosure>}><div>Trend visualization</div></ChartPanel>);
    expect(screen.queryByText("View as table")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.queryByText("Trend visualization")).toBeNull();
    expect(screen.getByText("1030 publications").closest("details")?.open).toBe(true);
    expect(screen.getByRole("link", { name: "Download CSV" }).getAttribute("href")).toBe("/export");
    fireEvent.click(screen.getByRole("button", { name: "Chart" }));
    expect(screen.getByText("Trend visualization")).toBeTruthy();
  });
  it("retains full record details in card view when a directory defaults to a table", () => {
    render(<ViewSwitcher label="Publication view" initialView="table" cards={<a href="/publications/example">Journal and DOI details</a>} table={<span>Publication table</span>} />);
    expect(screen.getByText("Publication table")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Cards" }));
    expect(screen.getByRole("link", { name: "Journal and DOI details" }).getAttribute("href")).toBe("/publications/example");
    fireEvent.click(screen.getByRole("button", { name: "Table" }));
    expect(screen.getByText("Publication table")).toBeTruthy();
  });
});
