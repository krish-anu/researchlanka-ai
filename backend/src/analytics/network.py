"""Centrality and community detection for the collaboration network.

The collaboration network is an undirected weighted graph: nodes are
institutions, countries or researchers, and an edge weight is the number of
publications two nodes co-authored. Sizes are small by construction -- the API
caps a network at 500 edges -- so these are the straightforward algorithms
rather than the ones that trade clarity for asymptotics.

Implemented here rather than pulled from a graph library for two reasons. The
runtime dependency list is deliberately short and fully pinned, and four
functions over a 500-edge graph do not justify adding to it. More importantly,
every figure this platform publishes has to be reproducible: the orderings and
tie-breaks below are fixed and explicit, so the same corpus always yields the
same centrality ranking and the same community labels. A library whose
community detection reseeds per run could not promise that.

Weights are *strengths*: a heavier edge means a closer collaboration. Shortest
path algorithms want the opposite, so distance is ``1 / weight`` -- the usual
convention for weighted collaboration networks. A pair that co-published ten
times is therefore ten times "closer" than a pair that co-published once.
"""

from __future__ import annotations

import heapq
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Mapping, Sequence


@dataclass(frozen=True)
class Edge:
    """One undirected weighted tie. ``source`` and ``target`` are node ids."""

    source: str
    target: str
    weight: float = 1.0


class Graph:
    """Undirected weighted graph with deterministic iteration order.

    Nodes and each node's neighbours are held in sorted order, so every
    traversal below visits them in the same sequence on every run. That is what
    makes label propagation reproducible.
    """

    def __init__(self, edges: Iterable[Edge], *, nodes: Iterable[str] = ()) -> None:
        adjacency: dict[str, dict[str, float]] = {node: {} for node in nodes}

        for edge in edges:
            if edge.source == edge.target:
                # A self-loop is a node collaborating with itself, which the
                # co-authorship construction cannot produce and which would
                # distort degree and modularity if it slipped through.
                continue
            weight = float(edge.weight)
            if weight <= 0:
                continue
            adjacency.setdefault(edge.source, {})
            adjacency.setdefault(edge.target, {})
            # Parallel edges accumulate rather than overwrite: two records
            # linking the same pair is a stronger tie, not a restated one.
            adjacency[edge.source][edge.target] = (
                adjacency[edge.source].get(edge.target, 0.0) + weight
            )
            adjacency[edge.target][edge.source] = (
                adjacency[edge.target].get(edge.source, 0.0) + weight
            )

        self._adjacency: dict[str, dict[str, float]] = {
            node: dict(sorted(neighbours.items()))
            for node, neighbours in sorted(adjacency.items())
        }

    @property
    def nodes(self) -> list[str]:
        return list(self._adjacency)

    @property
    def order(self) -> int:
        """Number of nodes."""

        return len(self._adjacency)

    @property
    def size(self) -> int:
        """Number of distinct undirected edges."""

        return sum(len(n) for n in self._adjacency.values()) // 2

    def neighbours(self, node: str) -> Mapping[str, float]:
        return self._adjacency.get(node, {})

    def degree(self, node: str) -> int:
        """Number of distinct neighbours."""

        return len(self._adjacency.get(node, {}))

    def strength(self, node: str) -> float:
        """Sum of incident edge weights -- the weighted degree."""

        return sum(self._adjacency.get(node, {}).values())

    def total_weight(self) -> float:
        """Sum of all edge weights, counting each undirected edge once."""

        return sum(sum(n.values()) for n in self._adjacency.values()) / 2.0

    @classmethod
    def from_edge_dicts(
        cls,
        edges: Sequence[Mapping[str, object]],
        *,
        nodes: Iterable[str] = (),
        source_key: str = "source",
        target_key: str = "target",
        weight_key: str = "weight",
    ) -> "Graph":
        """Build from the edge dictionaries the API already produces."""

        parsed: list[Edge] = []
        for edge in edges:
            source = edge.get(source_key)
            target = edge.get(target_key)
            if not isinstance(source, str) or not isinstance(target, str):
                continue
            raw_weight = edge.get(weight_key, 1.0)
            try:
                weight = float(raw_weight)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                weight = 1.0
            parsed.append(Edge(source, target, weight))
        return cls(parsed, nodes=nodes)


# --------------------------------------------------------------- components


def connected_components(graph: Graph) -> list[list[str]]:
    """Components, largest first, each sorted; ties broken on the first node.

    A collaboration network is usually one large component plus a scatter of
    isolated pairs, and several measures below are only defined within a
    component -- so this is the first thing every caller needs.
    """

    seen: set[str] = set()
    components: list[list[str]] = []

    for start in graph.nodes:
        if start in seen:
            continue
        queue = deque([start])
        seen.add(start)
        component = [start]
        while queue:
            node = queue.popleft()
            for neighbour in graph.neighbours(node):
                if neighbour not in seen:
                    seen.add(neighbour)
                    component.append(neighbour)
                    queue.append(neighbour)
        components.append(sorted(component))

    components.sort(key=lambda c: (-len(c), c[0]))
    return components


# --------------------------------------------------------------- centrality


def degree_centrality(graph: Graph) -> dict[str, float]:
    """Share of other nodes each node is directly tied to.

    Normalised by ``n - 1`` so the value is comparable across networks of
    different size, and so a value of 1.0 means "connected to everyone".
    """

    if graph.order <= 1:
        return {node: 0.0 for node in graph.nodes}
    scale = graph.order - 1
    return {node: graph.degree(node) / scale for node in graph.nodes}


def strength_centrality(graph: Graph) -> dict[str, float]:
    """Weighted degree: total collaborations, not distinct partners.

    Kept separate from :func:`degree_centrality` because the two answer
    different questions -- one institution may have many one-off partners while
    another has a few deep ties, and a ranking that conflated them would hide
    exactly the distinction the analytics are for.
    """

    return {node: graph.strength(node) for node in graph.nodes}


def _dijkstra(
    graph: Graph, source: str
) -> tuple[dict[str, float], dict[str, list[str]], list[str]]:
    """Weighted single-source shortest paths.

    Returns distances, the predecessors on shortest paths, and the nodes in
    non-decreasing distance order -- the three things Brandes' accumulation
    needs. Distance is ``1 / weight``, so a heavier tie is a shorter hop.
    """

    distance: dict[str, float] = {source: 0.0}
    predecessors: dict[str, list[str]] = {source: []}
    order: list[str] = []
    settled: set[str] = set()
    # The counter keeps the heap total-ordered when distances tie, so the visit
    # order cannot vary between runs on equal-weight graphs.
    counter = 0
    queue: list[tuple[float, int, str]] = [(0.0, counter, source)]

    while queue:
        dist, _, node = heapq.heappop(queue)
        if node in settled:
            continue
        settled.add(node)
        order.append(node)

        for neighbour, weight in graph.neighbours(node).items():
            candidate = dist + (1.0 / weight)
            known = distance.get(neighbour)
            if known is None or candidate < known - 1e-12:
                distance[neighbour] = candidate
                predecessors[neighbour] = [node]
                counter += 1
                heapq.heappush(queue, (candidate, counter, neighbour))
            elif (
                abs(candidate - known) <= 1e-12
                and node not in predecessors.get(neighbour, [])
            ):
                # An equally short second route: Brandes splits the dependency
                # across every shortest path, so both predecessors are kept.
                predecessors.setdefault(neighbour, []).append(node)

    return distance, predecessors, order


def betweenness_centrality(graph: Graph, *, normalized: bool = True) -> dict[str, float]:
    """Share of shortest paths running through each node (Brandes 2001).

    High betweenness marks a broker: an institution that, if removed, would
    disconnect groups with no other route to each other. On a collaboration
    network these are the bridging partners, which is a different and often
    more interesting list than the merely prolific ones.
    """

    betweenness: dict[str, float] = {node: 0.0 for node in graph.nodes}

    for source in graph.nodes:
        distance, predecessors, order = _dijkstra(graph, source)

        # Count shortest paths to each node, in non-decreasing distance order.
        sigma: dict[str, float] = {node: 0.0 for node in distance}
        sigma[source] = 1.0
        for node in order:
            for predecessor in predecessors.get(node, []):
                sigma[node] += sigma[predecessor]

        # Accumulate dependencies back-to-front.
        delta: dict[str, float] = {node: 0.0 for node in distance}
        for node in reversed(order):
            for predecessor in predecessors.get(node, []):
                if sigma[node] > 0:
                    delta[predecessor] += (sigma[predecessor] / sigma[node]) * (
                        1.0 + delta[node]
                    )
            if node != source:
                betweenness[node] += delta[node]

    # Each undirected pair was counted once from either endpoint.
    for node in betweenness:
        betweenness[node] /= 2.0

    if normalized and graph.order > 2:
        scale = 2.0 / ((graph.order - 1) * (graph.order - 2))
        for node in betweenness:
            betweenness[node] *= scale

    return betweenness


def closeness_centrality(graph: Graph) -> dict[str, float]:
    """How near a node sits to everything it can reach.

    Uses the Wasserman-Faust correction: the raw inverse mean distance is
    scaled by the fraction of the network the node reaches at all. Without it a
    node in a tight two-node island scores a perfect 1.0 and outranks a
    genuinely central node in the main component -- inverting the ranking
    exactly where a collaboration network is most fragmented.
    """

    closeness: dict[str, float] = {}
    reachable_scale = graph.order - 1

    for node in graph.nodes:
        distance, _, _ = _dijkstra(graph, node)
        others = {n: d for n, d in distance.items() if n != node}
        total = sum(others.values())
        if total <= 0 or reachable_scale <= 0:
            closeness[node] = 0.0
            continue
        # (reached / (n-1)) * (reached / summed distance)
        closeness[node] = (len(others) / reachable_scale) * (len(others) / total)

    return closeness


# -------------------------------------------------------------- communities


def label_propagation_communities(
    graph: Graph, *, max_iterations: int = 100
) -> dict[str, int]:
    """Partition the network into communities (Raghavan et al. 2007).

    Each node repeatedly takes the label carried by the greatest total edge
    weight among its neighbours. The published algorithm randomises node order
    and breaks ties at random, which makes successive runs disagree; both are
    made deterministic here -- nodes are visited in sorted order and ties go to
    the smallest label -- because a community assignment that changed between
    runs could not be cited.

    Labels are renumbered at the end so community ids are stable, contiguous
    integers ordered by descending community size.
    """

    if graph.order == 0:
        return {}

    labels: dict[str, str] = {node: node for node in graph.nodes}

    for _ in range(max_iterations):
        changed = False
        for node in graph.nodes:
            neighbours = graph.neighbours(node)
            if not neighbours:
                continue
            weight_by_label: dict[str, float] = {}
            for neighbour, weight in neighbours.items():
                label = labels[neighbour]
                weight_by_label[label] = weight_by_label.get(label, 0.0) + weight
            # Heaviest label wins; the smallest label id settles a tie.
            best = min(weight_by_label.items(), key=lambda item: (-item[1], item[0]))[0]
            if labels[node] != best:
                labels[node] = best
                changed = True
        if not changed:
            break

    return _renumber_by_size(labels)


def _renumber_by_size(labels: Mapping[str, str]) -> dict[str, int]:
    """Map arbitrary label keys onto 0..k-1, largest community first."""

    members: dict[str, list[str]] = {}
    for node, label in labels.items():
        members.setdefault(label, []).append(node)

    ordered = sorted(members.items(), key=lambda item: (-len(item[1]), item[0]))
    return {
        node: index
        for index, (_, community) in enumerate(ordered)
        for node in community
    }


def modularity(graph: Graph, communities: Mapping[str, int]) -> float:
    """Newman-Girvan modularity Q of a partition, weighted.

    Q compares the weight falling inside communities against what random
    rewiring of the same degree sequence would produce. Roughly: above about
    0.3 the community structure is real, near 0 the partition says nothing.
    Reported alongside the partition so a reader can judge whether the
    communities are worth interpreting rather than taking them on trust.
    """

    total = graph.total_weight()
    if total <= 0:
        return 0.0

    inside: dict[int, float] = {}
    degree_sum: dict[int, float] = {}

    for node in graph.nodes:
        community = communities.get(node)
        if community is None:
            continue
        degree_sum[community] = degree_sum.get(community, 0.0) + graph.strength(node)
        for neighbour, weight in graph.neighbours(node).items():
            if communities.get(neighbour) == community:
                inside[community] = inside.get(community, 0.0) + weight

    q = 0.0
    for community, degrees in degree_sum.items():
        # inside[] counts each internal edge from both ends, which is the 2m
        # convention the formula expects.
        q += (inside.get(community, 0.0) / (2.0 * total)) - (
            degrees / (2.0 * total)
        ) ** 2
    return q


# ------------------------------------------------------------------ summary


@dataclass
class NetworkMetrics:
    """Per-node measures plus the graph-level context needed to read them."""

    degree: dict[str, float] = field(default_factory=dict)
    strength: dict[str, float] = field(default_factory=dict)
    betweenness: dict[str, float] = field(default_factory=dict)
    closeness: dict[str, float] = field(default_factory=dict)
    community: dict[str, int] = field(default_factory=dict)
    node_count: int = 0
    edge_count: int = 0
    density: float = 0.0
    component_count: int = 0
    largest_component_size: int = 0
    community_count: int = 0
    modularity: float = 0.0

    def for_node(self, node: str) -> dict[str, float | int]:
        return {
            "degree_centrality": round(self.degree.get(node, 0.0), 6),
            "strength": round(self.strength.get(node, 0.0), 6),
            "betweenness_centrality": round(self.betweenness.get(node, 0.0), 6),
            "closeness_centrality": round(self.closeness.get(node, 0.0), 6),
            "community": self.community.get(node, -1),
        }

    def summary(self) -> dict[str, float | int]:
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "density": round(self.density, 6),
            "component_count": self.component_count,
            "largest_component_size": self.largest_component_size,
            "community_count": self.community_count,
            "modularity": round(self.modularity, 6),
        }


def analyse(graph: Graph) -> NetworkMetrics:
    """Every measure in one pass over the graph, for the API to attach."""

    components = connected_components(graph)
    community = label_propagation_communities(graph)

    order = graph.order
    possible_edges = order * (order - 1) / 2 if order > 1 else 0

    return NetworkMetrics(
        degree=degree_centrality(graph),
        strength=strength_centrality(graph),
        betweenness=betweenness_centrality(graph),
        closeness=closeness_centrality(graph),
        community=community,
        node_count=order,
        edge_count=graph.size,
        density=(graph.size / possible_edges) if possible_edges else 0.0,
        component_count=len(components),
        largest_component_size=len(components[0]) if components else 0,
        community_count=len(set(community.values())) if community else 0,
        modularity=modularity(graph, community),
    )
