import type {
  CollaborationNetwork,
  NetworkEdge,
  NetworkNode,
} from "@/types/api";

function maxNumber(a: number | undefined, b: number | undefined): number {
  return Math.max(a ?? 0, b ?? 0);
}

function mergeNode(existing: NetworkNode, next: NetworkNode): NetworkNode {
  return {
    ...existing,
    label: existing.label || next.label,
    publication_count: maxNumber(existing.publication_count, next.publication_count),
    first_year:
      existing.first_year == null
        ? next.first_year
        : next.first_year == null
          ? existing.first_year
          : Math.min(existing.first_year, next.first_year),
    last_year:
      existing.last_year == null
        ? next.last_year
        : next.last_year == null
          ? existing.last_year
          : Math.max(existing.last_year, next.last_year),
    degree_centrality: maxNumber(existing.degree_centrality, next.degree_centrality),
    strength: maxNumber(existing.strength, next.strength),
    betweenness_centrality: maxNumber(
      existing.betweenness_centrality,
      next.betweenness_centrality,
    ),
    closeness_centrality: maxNumber(
      existing.closeness_centrality,
      next.closeness_centrality,
    ),
    community: Math.min(existing.community, next.community),
  };
}

function orderedEdgeKey(edge: NetworkEdge): string {
  return [edge.source, edge.target].sort().join("::");
}

function mergeEdge(existing: NetworkEdge, next: NetworkEdge): NetworkEdge {
  return {
    ...existing,
    weight: existing.weight + next.weight,
    first_year:
      existing.first_year == null
        ? next.first_year
        : next.first_year == null
          ? existing.first_year
          : Math.min(existing.first_year, next.first_year),
    last_year:
      existing.last_year == null
        ? next.last_year
        : next.last_year == null
          ? existing.last_year
          : Math.max(existing.last_year, next.last_year),
  };
}

export function networkForDisplay(network: CollaborationNetwork): CollaborationNetwork {
  const nodesById = new Map<string, NetworkNode>();

  for (const node of network.nodes) {
    const existing = nodesById.get(node.id);
    nodesById.set(node.id, existing ? mergeNode(existing, node) : node);
  }

  const edgeByPair = new Map<string, NetworkEdge>();
  for (const edge of network.edges) {
    if (edge.source === edge.target) continue;
    if (!nodesById.has(edge.source) || !nodesById.has(edge.target)) continue;
    const key = orderedEdgeKey(edge);
    const existing = edgeByPair.get(key);
    edgeByPair.set(key, existing ? mergeEdge(existing, edge) : edge);
  }

  return {
    ...network,
    nodes: [...nodesById.values()],
    edges: [...edgeByPair.values()],
  };
}

/** Keep only the connected component containing a profile's focal entity. */
export function networkComponentForLabel(
  network: CollaborationNetwork,
  label: string,
): CollaborationNetwork {
  const display = networkForDisplay(network);
  const normalizedLabel = label.trim().toLocaleLowerCase();
  const root = display.nodes.find(
    (node) => node.label.trim().toLocaleLowerCase() === normalizedLabel,
  );
  if (!root) return display;

  const adjacency = new Map<string, Set<string>>();
  for (const node of display.nodes) adjacency.set(node.id, new Set());
  for (const edge of display.edges) {
    adjacency.get(edge.source)?.add(edge.target);
    adjacency.get(edge.target)?.add(edge.source);
  }

  const included = new Set([root.id]);
  const pending = [root.id];
  while (pending.length > 0) {
    const current = pending.pop();
    if (!current) continue;
    for (const neighbor of adjacency.get(current) ?? []) {
      if (included.has(neighbor)) continue;
      included.add(neighbor);
      pending.push(neighbor);
    }
  }

  return {
    ...display,
    nodes: display.nodes.filter((node) => included.has(node.id)),
    edges: display.edges.filter(
      (edge) => included.has(edge.source) && included.has(edge.target),
    ),
  };
}
