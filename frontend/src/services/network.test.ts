import { describe, expect, it } from "vitest";

import { networkForDisplay } from "./network";
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
