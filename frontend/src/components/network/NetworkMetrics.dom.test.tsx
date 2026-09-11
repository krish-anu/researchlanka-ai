/**
 * @vitest-environment jsdom
 */
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  NetworkBrokersTable,
  NetworkSummaryPanel,
} from "@/components/network/NetworkMetrics";
import type { NetworkNode, NetworkSummary } from "@/types/api";

// next/link needs the router context it cannot have here; the anchor is all
// these tests care about.
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: React.ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

afterEach(cleanup);

function summary(overrides: Partial<NetworkSummary> = {}): NetworkSummary {
  return {
    node_count: 10,
    edge_count: 14,
    density: 0.311,
    component_count: 1,
    largest_component_size: 10,
    community_count: 3,
    modularity: 0.62,
    ...overrides,
  };
}

function node(overrides: Partial<NetworkNode> = {}): NetworkNode {
  return {
    id: "university-of-colombo",
    label: "University of Colombo",
    type: "institution",
    publication_count: 100,
    degree_centrality: 0.4,
    strength: 30,
    betweenness_centrality: 0.1,
    closeness_centrality: 0.5,
    community: 0,
    ...overrides,
  };
}

describe("NetworkSummaryPanel", () => {
  it("reports the structural figures", () => {
    render(<NetworkSummaryPanel summary={summary()} />);

    expect(screen.getByText("10")).toBeDefined();
    expect(screen.getByText("14")).toBeDefined();
    expect(screen.getByText("0.311")).toBeDefined();
  });

  it("calls a strong community split real", () => {
    render(<NetworkSummaryPanel summary={summary({ modularity: 0.62 })} />);

    expect(screen.getByText(/above the conventional 0.3 floor/)).toBeDefined();
  });

  it("warns plainly when modularity is too low to interpret", () => {
    // The panel must not present a community count as a finding when the graph
    // does not actually divide — that is the difference between a result and an
    // artefact of the algorithm.
    render(<NetworkSummaryPanel summary={summary({ modularity: 0.05 })} />);

    expect(screen.getByText(/below the conventional 0.3 floor/)).toBeDefined();
    expect(screen.getByText(/suggestive rather than as findings/)).toBeDefined();
  });

  it("treats the 0.3 floor as inclusive", () => {
    render(<NetworkSummaryPanel summary={summary({ modularity: 0.3 })} />);

    expect(screen.getByText(/above the conventional 0.3 floor/)).toBeDefined();
  });

  it("says the graph is fragmented and how large the largest piece is", () => {
    render(
      <NetworkSummaryPanel
        summary={summary({ component_count: 5, largest_component_size: 2 })}
      />,
    );

    expect(screen.getByText(/largest holds 2/)).toBeDefined();
  });

  it("says so when the graph is a single connected component", () => {
    render(<NetworkSummaryPanel summary={summary({ component_count: 1 })} />);

    expect(screen.getByText("single connected graph")).toBeDefined();
  });

  it("renders nothing when an older API sent no summary", () => {
    // The graph above it still draws; a missing summary must not blank the page.
    const { container } = render(<NetworkSummaryPanel summary={undefined} />);

    expect(container.firstChild).toBeNull();
  });
});

describe("NetworkBrokersTable", () => {
  const nodes = [
    node({ id: "a", label: "Alpha", betweenness_centrality: 0.1, publication_count: 900 }),
    node({ id: "b", label: "Bravo", betweenness_centrality: 0.9, publication_count: 10 }),
    node({ id: "c", label: "Charlie", betweenness_centrality: 0.5, publication_count: 400 }),
  ];

  it("ranks by brokerage, not by volume", () => {
    // The whole point of the table: the biggest publisher is not the broker.
    render(<NetworkBrokersTable nodes={nodes} />);

    const rows = screen.getAllByRole("row").slice(1); // drop the header
    const order = rows.map((row) => within(row).getAllByRole("cell")[0].textContent);

    expect(order).toEqual(["Bravo", "Charlie", "Alpha"]);
  });

  it("breaks a betweenness tie on publication count, then on name", () => {
    render(
      <NetworkBrokersTable
        nodes={[
          node({ id: "x", label: "Xray", betweenness_centrality: 0.5, publication_count: 10 }),
          node({ id: "y", label: "Yankee", betweenness_centrality: 0.5, publication_count: 99 }),
        ]}
      />,
    );

    const first = screen.getAllByRole("row")[1];
    expect(within(first).getAllByRole("cell")[0].textContent).toBe("Yankee");
  });

  it("honours the row limit", () => {
    const many = Array.from({ length: 20 }, (_, i) =>
      node({ id: `n${i}`, label: `Node ${i}`, betweenness_centrality: 1 - i / 100 }),
    );

    render(<NetworkBrokersTable nodes={many} limit={5} />);

    expect(screen.getAllByRole("row").slice(1)).toHaveLength(5);
  });

  it("explains itself instead of ranking arbitrarily when nobody brokers", () => {
    // Every betweenness zero means a complete graph or only isolated pairs. An
    // order would be meaningless, so the table must not present one.
    render(
      <NetworkBrokersTable
        nodes={nodes.map((n) => ({ ...n, betweenness_centrality: 0 }))}
      />,
    );

    expect(screen.queryByRole("table")).toBeNull();
    expect(screen.getByText(/no brokers to rank/)).toBeDefined();
  });

  it("handles an empty network", () => {
    render(<NetworkBrokersTable nodes={[]} />);

    expect(screen.queryByRole("table")).toBeNull();
  });

  it("links institutions and researchers to their profiles", () => {
    render(
      <NetworkBrokersTable
        nodes={[node({ label: "University of Colombo", betweenness_centrality: 0.5 })]}
      />,
    );

    expect(screen.getByRole("link", { name: "University of Colombo" })).toHaveProperty(
      "href",
      expect.stringContaining("/institutions/"),
    );
  });

  it("does not link countries, which have no profile route", () => {
    render(
      <NetworkBrokersTable
        nodes={[
          node({ id: "lk", label: "Sri Lanka", type: "country", betweenness_centrality: 0.5 }),
        ]}
      />,
    );

    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("Sri Lanka")).toBeDefined();
  });
});
