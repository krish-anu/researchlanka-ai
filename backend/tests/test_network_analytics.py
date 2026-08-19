"""Tests for collaboration-network centrality and community detection.

Every expected value here is derived by hand from the graph's structure rather
than recorded from a previous run, so the suite catches a wrong answer rather
than merely a changed one. The graphs are the canonical ones -- path, star,
triangle, barbell -- whose centralities are standard results.
"""

from __future__ import annotations

import pytest

from src.analytics.network import (
    Edge,
    Graph,
    analyse,
    betweenness_centrality,
    closeness_centrality,
    connected_components,
    degree_centrality,
    label_propagation_communities,
    modularity,
    strength_centrality,
)


def approx(value: float) -> float:
    return pytest.approx(value, abs=1e-9)


# ------------------------------------------------------------------- graph


def test_graph_treats_edges_as_undirected_and_sums_parallel_edges():
    graph = Graph([Edge("a", "b", 2.0), Edge("b", "a", 3.0)])

    assert graph.order == 2
    assert graph.size == 1
    # The same pair seen twice is one stronger tie, not two ties.
    assert graph.strength("a") == approx(5.0)
    assert graph.neighbours("a")["b"] == approx(5.0)
    assert graph.neighbours("b")["a"] == approx(5.0)


def test_graph_drops_self_loops_and_non_positive_weights():
    graph = Graph(
        [Edge("a", "a", 4.0), Edge("a", "b", 0.0), Edge("a", "b", -1.0), Edge("a", "c", 1.0)]
    )

    assert graph.size == 1
    assert graph.degree("a") == 1
    assert "a" not in graph.neighbours("a")


def test_isolated_nodes_are_kept_when_passed_explicitly():
    # A node with no collaborations is still part of the network, and dropping
    # it would silently inflate every normalised centrality.
    graph = Graph([Edge("a", "b", 1.0)], nodes=["a", "b", "lonely"])

    assert graph.order == 3
    assert graph.degree("lonely") == 0
    assert degree_centrality(graph)["lonely"] == approx(0.0)


def test_from_edge_dicts_reads_the_api_edge_shape_and_skips_malformed_rows():
    graph = Graph.from_edge_dicts(
        [
            {"source": "a", "target": "b", "weight": 3},
            {"source": "b", "target": "c"},  # weight defaults to 1
            {"source": None, "target": "c", "weight": 9},  # unusable
            {"source": "c", "target": "d", "weight": "not-a-number"},
        ]
    )

    assert graph.order == 4
    assert graph.neighbours("a")["b"] == approx(3.0)
    assert graph.neighbours("b")["c"] == approx(1.0)
    # A weight that will not parse falls back to 1.0 rather than dropping a
    # real collaboration.
    assert graph.neighbours("c")["d"] == approx(1.0)


# -------------------------------------------------------------- components


def test_connected_components_are_ordered_largest_first():
    graph = Graph(
        [Edge("a", "b"), Edge("b", "c"), Edge("x", "y")], nodes=["a", "b", "c", "x", "y", "z"]
    )

    assert connected_components(graph) == [["a", "b", "c"], ["x", "y"], ["z"]]


# -------------------------------------------------------------- centrality


def test_degree_centrality_on_a_star_is_one_at_the_hub():
    # Star: hub touches all 3 others (3/3 = 1.0); each leaf touches 1 (1/3).
    graph = Graph([Edge("hub", "a"), Edge("hub", "b"), Edge("hub", "c")])
    centrality = degree_centrality(graph)

    assert centrality["hub"] == approx(1.0)
    assert centrality["a"] == approx(1 / 3)
    assert centrality["b"] == approx(1 / 3)
    assert centrality["c"] == approx(1 / 3)


def test_strength_and_degree_separate_many_weak_ties_from_few_strong_ones():
    # "broad" has three one-off partners; "deep" has one ten-publication tie.
    graph = Graph(
        [
            Edge("broad", "p1", 1.0),
            Edge("broad", "p2", 1.0),
            Edge("broad", "p3", 1.0),
            Edge("deep", "q1", 10.0),
        ]
    )
    degree = degree_centrality(graph)
    strength = strength_centrality(graph)

    assert degree["broad"] > degree["deep"]
    assert strength["deep"] > strength["broad"]


def test_betweenness_is_one_for_the_middle_of_a_path_and_zero_at_the_ends():
    # P3: every shortest path between a and c runs through b, and that is the
    # only pair not counting an endpoint -- so normalised betweenness is 1.
    graph = Graph([Edge("a", "b"), Edge("b", "c")])
    betweenness = betweenness_centrality(graph)

    assert betweenness["b"] == approx(1.0)
    assert betweenness["a"] == approx(0.0)
    assert betweenness["c"] == approx(0.0)


def test_betweenness_is_zero_everywhere_in_a_triangle():
    # Everyone is adjacent to everyone, so no node ever sits on another pair's
    # shortest path.
    graph = Graph([Edge("a", "b"), Edge("b", "c"), Edge("a", "c")])

    assert betweenness_centrality(graph) == {
        "a": approx(0.0),
        "b": approx(0.0),
        "c": approx(0.0),
    }


def test_betweenness_splits_credit_across_equally_short_parallel_routes():
    # 4-cycle: a and c are joined by two equally short routes, through b and
    # through d, so each broker carries half of that pair's single path.
    # Normalisation for n=4 is 2/((4-1)(4-2)) = 1/3, giving 0.5 * 1/3.
    graph = Graph([Edge("a", "b"), Edge("b", "c"), Edge("c", "d"), Edge("d", "a")])
    betweenness = betweenness_centrality(graph)

    for node in "abcd":
        assert betweenness[node] == approx(1 / 6)


def test_betweenness_identifies_the_bridge_in_a_barbell():
    # Two triangles joined by a single edge c--x. Every path from the left
    # triangle to the right one crosses both c and x, so those two are the
    # brokers and the four outer nodes broker nothing.
    graph = Graph(
        [
            Edge("a", "b"),
            Edge("b", "c"),
            Edge("a", "c"),
            Edge("x", "y"),
            Edge("y", "z"),
            Edge("x", "z"),
            Edge("c", "x"),
        ]
    )
    betweenness = betweenness_centrality(graph)

    assert betweenness["c"] == approx(betweenness["x"])
    assert betweenness["c"] > betweenness["a"]
    for outer in ("a", "b", "y", "z"):
        assert betweenness[outer] == approx(0.0)


def test_heavier_collaboration_counts_as_a_shorter_path():
    # Distance is 1/weight. Route a-b-c costs 1/10 + 1/10 = 0.2; the direct
    # a-c edge costs 1/1 = 1.0. So b sits on the shortest path despite a and c
    # being directly tied, and the direct edge is the detour.
    graph = Graph([Edge("a", "b", 10.0), Edge("b", "c", 10.0), Edge("a", "c", 1.0)])

    assert betweenness_centrality(graph)["b"] == approx(1.0)


def test_closeness_prefers_the_hub_and_penalises_an_unreachable_island():
    # Without the Wasserman-Faust correction the two island nodes would each
    # score a perfect 1.0 -- they are one hop from everything they can reach --
    # and outrank the hub of the main component. The correction scales by how
    # much of the network is reachable, so the hub wins.
    graph = Graph(
        [Edge("hub", "a"), Edge("hub", "b"), Edge("hub", "c"), Edge("island1", "island2")]
    )
    closeness = closeness_centrality(graph)

    assert closeness["hub"] > closeness["island1"]
    assert closeness["hub"] > closeness["a"]


def test_centrality_of_an_empty_or_single_node_graph_does_not_divide_by_zero():
    empty = Graph([])
    assert degree_centrality(empty) == {}
    assert betweenness_centrality(empty) == {}
    assert closeness_centrality(empty) == {}

    single = Graph([], nodes=["only"])
    assert degree_centrality(single) == {"only": approx(0.0)}
    assert closeness_centrality(single) == {"only": approx(0.0)}


# -------------------------------------------------------------- communities


def test_label_propagation_separates_two_cliques_joined_by_a_weak_bridge():
    graph = Graph(
        [
            Edge("a", "b", 5.0),
            Edge("b", "c", 5.0),
            Edge("a", "c", 5.0),
            Edge("x", "y", 5.0),
            Edge("y", "z", 5.0),
            Edge("x", "z", 5.0),
            Edge("c", "x", 1.0),
        ]
    )
    communities = label_propagation_communities(graph)

    assert communities["a"] == communities["b"] == communities["c"]
    assert communities["x"] == communities["y"] == communities["z"]
    assert communities["a"] != communities["x"]


def test_community_ids_are_contiguous_and_ordered_by_descending_size():
    graph = Graph(
        [
            Edge("a", "b", 5.0),
            Edge("b", "c", 5.0),
            Edge("a", "c", 5.0),
            Edge("a", "d", 5.0),
            Edge("b", "d", 5.0),
            Edge("x", "y", 5.0),
        ]
    )
    communities = label_propagation_communities(graph)
    sizes = sorted(
        (list(communities.values()).count(c) for c in set(communities.values())),
        reverse=True,
    )

    assert set(communities.values()) == set(range(len(set(communities.values()))))
    assert communities["a"] == 0  # the larger community takes id 0
    assert sizes == [4, 2]


def test_community_assignment_is_identical_across_repeated_runs():
    # The published algorithm randomises node order and tie-breaks; this one
    # must not, or a published community could not be reproduced.
    edges = [
        Edge("a", "b", 2.0),
        Edge("b", "c", 2.0),
        Edge("c", "a", 2.0),
        Edge("c", "d", 1.0),
        Edge("d", "e", 2.0),
        Edge("e", "f", 2.0),
        Edge("f", "d", 2.0),
    ]
    first = label_propagation_communities(Graph(edges))

    for _ in range(25):
        assert label_propagation_communities(Graph(edges)) == first
    # Edge insertion order must not matter either.
    assert label_propagation_communities(Graph(list(reversed(edges)))) == first


def test_modularity_is_high_for_real_structure_and_zero_for_one_big_community():
    graph = Graph(
        [
            Edge("a", "b", 5.0),
            Edge("b", "c", 5.0),
            Edge("a", "c", 5.0),
            Edge("x", "y", 5.0),
            Edge("y", "z", 5.0),
            Edge("x", "z", 5.0),
            Edge("c", "x", 1.0),
        ]
    )

    split = label_propagation_communities(graph)
    assert modularity(graph, split) > 0.3  # conventional "real structure" floor

    # Putting every node in one community is the degenerate partition, whose
    # modularity is exactly 0 by construction.
    everything = {node: 0 for node in graph.nodes}
    assert modularity(graph, everything) == approx(0.0)


def test_modularity_of_an_empty_graph_is_zero_rather_than_a_division_error():
    assert modularity(Graph([]), {}) == approx(0.0)


# ------------------------------------------------------------------ summary


def test_analyse_reports_every_measure_and_the_graph_level_context():
    graph = Graph(
        [
            Edge("a", "b", 5.0),
            Edge("b", "c", 5.0),
            Edge("a", "c", 5.0),
            Edge("x", "y", 5.0),
        ],
        nodes=["a", "b", "c", "x", "y", "alone"],
    )
    metrics = analyse(graph)
    summary = metrics.summary()

    assert summary["node_count"] == 6
    assert summary["edge_count"] == 4
    # 4 of the 15 possible pairs among 6 nodes are joined.
    assert summary["density"] == pytest.approx(4 / 15, abs=1e-6)
    assert summary["component_count"] == 3  # triangle, pair, isolate
    assert summary["largest_component_size"] == 3

    node = metrics.for_node("a")
    assert set(node) == {
        "degree_centrality",
        "strength",
        "betweenness_centrality",
        "closeness_centrality",
        "community",
    }
    assert node["strength"] == approx(10.0)


def test_analyse_of_an_empty_network_returns_zeroed_context_not_an_error():
    summary = analyse(Graph([])).summary()

    assert summary["node_count"] == 0
    assert summary["edge_count"] == 0
    assert summary["density"] == approx(0.0)
    assert summary["component_count"] == 0
    assert summary["community_count"] == 0
    assert summary["modularity"] == approx(0.0)
