import { describe, expect, it } from "vitest";

import { networkComponentForLabel, networkForDisplay } from "./network";
import type { CollaborationNetwork, NetworkNode } from "@/types/api";

function node(overrides: Partial<NetworkNode>): NetworkNode {
  return {
    id: "researcher-a",
    label: "Researcher A",
    type: "researcher",
    publication_count: 1,
    degree_centrality: 0,
    strength: 1,
    betweenness_centrality: 0,
    closeness_centrality: 0,
    community: 0,
    ...overrides,
  };
}

describe("networkForDisplay", () => {
  it("deduplicates nodes by id and merges duplicate undirected edges", () => {
    const network: CollaborationNetwork = {
      nodes: [
        node({ id: "kugathasan-a", label: "Kugathasan A", publication_count: 2, strength: 4 }),
        node({ id: "kugathasan-a", label: "Kugathasan A", publication_count: 5, strength: 2 }),
        node({ id: "kasthurirathna-d", label: "Kasthurirathna D" }),
      ],
      edges: [
        { source: "kugathasan-a", target: "kasthurirathna-d", weight: 2 },
        { source: "kasthurirathna-d", target: "kugathasan-a", weight: 3 },
        { source: "kugathasan-a", target: "kugathasan-a", weight: 99 },
      ],
      summary: {
        node_count: 3,
        edge_count: 3,
        density: 1,
        component_count: 1,
        largest_component_size: 3,
        community_count: 1,
        modularity: 0,
      },
    };

    const display = networkForDisplay(network);

    expect(display.nodes.map((item) => item.id)).toEqual([
      "kugathasan-a",
      "kasthurirathna-d",
    ]);
    expect(display.nodes[0].publication_count).toBe(5);
    expect(display.nodes[0].strength).toBe(4);
    expect(display.edges).toEqual([
      { source: "kugathasan-a", target: "kasthurirathna-d", weight: 5 },
    ]);
  });
});

describe("networkComponentForLabel", () => {
  it("removes disconnected components from an institution profile network", () => {
    const network: CollaborationNetwork = {
      nodes: [
        node({ id: "moratuwa", label: "University of Moratuwa", type: "institution" }),
        node({ id: "colombo", label: "University of Colombo", type: "institution" }),
        node({ id: "alpha", label: "Alpha Institute", type: "institution", community: 1 }),
        node({ id: "beta", label: "Beta Institute", type: "institution", community: 1 }),
      ],
      edges: [
        { source: "moratuwa", target: "colombo", weight: 4 },
        { source: "alpha", target: "beta", weight: 3 },
      ],
      summary: {
        node_count: 4,
        edge_count: 2,
        density: 1 / 3,
        component_count: 2,
        largest_component_size: 2,
        community_count: 2,
        modularity: 0.5,
      },
    };

    const component = networkComponentForLabel(network, "University of Moratuwa");

    expect(component.nodes.map((item) => item.id)).toEqual(["moratuwa", "colombo"]);
    expect(component.edges).toEqual([
      { source: "moratuwa", target: "colombo", weight: 4 },
    ]);
  });

  it("keeps the full response when the focal label is absent", () => {
    const network: CollaborationNetwork = {
      nodes: [node({ id: "alpha", label: "Alpha" })],
      edges: [],
      summary: {
        node_count: 1,
        edge_count: 0,
        density: 0,
        component_count: 1,
        largest_component_size: 1,
        community_count: 1,
        modularity: 0,
      },
    };

    expect(networkComponentForLabel(network, "Missing").nodes).toHaveLength(1);
  });
});
