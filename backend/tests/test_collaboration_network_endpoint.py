"""The collaboration-network endpoint, from publication rows to enriched graph.

Exercises the real repository method rather than a fake, by replacing only its
SQL read. Everything downstream of that -- co-authorship pair counting, the
weight and limit filters, and the centrality/community enrichment -- is the
production code path.
"""

from __future__ import annotations

import pytest

from src.api.repositories.postgres import PostgresPublicationRepository


def repository_over(rows: list[dict[str, object]]) -> PostgresPublicationRepository:
    """A repository whose only stubbed part is the database read."""

    repository = PostgresPublicationRepository(connection_factory=lambda dsn: None)
    repository.list_publications = lambda *args, **kwargs: {  # type: ignore[method-assign]
        "records": rows,
        "total": len(rows),
        "facets": None,
        "meta": {},
    }
    return repository


# Two institution clusters that co-publish internally and meet on one paper.
# Colombo and Peradeniya share four papers; Moratuwa and Ruhuna share three;
# a single paper joins Peradeniya to Moratuwa, which is the only bridge.
CLUSTERED_ROWS: list[dict[str, object]] = (
    [{"institutions": "University of Colombo;University of Peradeniya"}] * 4
    + [{"institutions": "University of Moratuwa;University of Ruhuna"}] * 3
    + [{"institutions": "University of Peradeniya;University of Moratuwa"}]
)


def test_nodes_carry_centrality_and_community_and_the_response_carries_a_summary():
    result = repository_over(CLUSTERED_ROWS).collaboration_network(
        {}, scope="institution", min_weight=1, limit=100
    )

    assert set(result) == {"nodes", "edges", "summary"}
    for node in result["nodes"]:
        assert set(node) >= {
            "id",
            "label",
            "type",
            "publication_count",
            "degree_centrality",
            "strength",
            "betweenness_centrality",
            "closeness_centrality",
            "community",
        }

    summary = result["summary"]
    assert summary["node_count"] == 4
    assert summary["edge_count"] == 3
    assert summary["component_count"] == 1


def test_the_bridging_institutions_outrank_the_leaves_on_betweenness():
    result = repository_over(CLUSTERED_ROWS).collaboration_network(
        {}, scope="institution", min_weight=1, limit=100
    )
    betweenness = {n["id"]: n["betweenness_centrality"] for n in result["nodes"]}

    # Peradeniya and Moratuwa are the only route between the two clusters.
    assert betweenness["university-of-peradeniya"] > betweenness["university-of-colombo"]
    assert betweenness["university-of-moratuwa"] > betweenness["university-of-ruhuna"]
    assert betweenness["university-of-colombo"] == pytest.approx(0.0)


def test_edge_weight_counts_co_publications_and_min_weight_drops_weak_ties():
    unfiltered = repository_over(CLUSTERED_ROWS).collaboration_network(
        {}, scope="institution", min_weight=1, limit=100
    )
    weights = {(e["source"], e["target"]): e["weight"] for e in unfiltered["edges"]}
    assert weights[("university-of-colombo", "university-of-peradeniya")] == 4

    # Raising the floor to 3 removes the single-paper bridge, which should
    # split the network into the two clusters it was holding together.
    filtered = repository_over(CLUSTERED_ROWS).collaboration_network(
        {}, scope="institution", min_weight=3, limit=100
    )
    assert filtered["summary"]["edge_count"] == 2
    assert filtered["summary"]["component_count"] == 2


def test_communities_follow_the_clusters_rather_than_the_bridge():
    result = repository_over(CLUSTERED_ROWS).collaboration_network(
        {}, scope="institution", min_weight=1, limit=100
    )
    community = {n["id"]: n["community"] for n in result["nodes"]}

    assert community["university-of-colombo"] == community["university-of-peradeniya"]
    assert community["university-of-moratuwa"] == community["university-of-ruhuna"]
    assert community["university-of-colombo"] != community["university-of-moratuwa"]
    assert result["summary"]["community_count"] == 2
    assert result["summary"]["modularity"] > 0.0


def test_metrics_describe_the_returned_graph_after_the_limit_is_applied():
    # Ten disjoint pairs, but the response is capped at three edges. The
    # summary has to describe those three, not the ten the corpus contains --
    # otherwise the numbers would not match the graph a reader is looking at.
    rows = [{"institutions": f"Institute {i}A;Institute {i}B"} for i in range(10)]
    result = repository_over(rows).collaboration_network(
        {}, scope="institution", min_weight=1, limit=3
    )

    assert len(result["edges"]) == 3
    assert result["summary"]["node_count"] == 6
    assert result["summary"]["edge_count"] == 3
    assert result["summary"]["component_count"] == 3


def test_an_empty_corpus_returns_an_empty_graph_rather_than_failing():
    result = repository_over([]).collaboration_network(
        {}, scope="institution", min_weight=1, limit=100
    )

    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["summary"]["node_count"] == 0
    assert result["summary"]["modularity"] == pytest.approx(0.0)


def test_single_institution_papers_produce_no_edges_and_so_no_network():
    # A paper with one institution has no co-authorship pair to contribute.
    rows = [{"institutions": "University of Colombo"}] * 5
    result = repository_over(rows).collaboration_network(
        {}, scope="institution", min_weight=1, limit=100
    )

    assert result["edges"] == []
    assert result["nodes"] == []


@pytest.mark.parametrize(
    ("scope", "column"),
    [("institution", "institutions"), ("country", "countries"), ("researcher", "authors")],
)
def test_every_scope_reads_its_own_column_and_is_enriched_the_same_way(scope, column):
    rows = [{column: "Alpha;Beta"}, {column: "Beta;Gamma"}]
    result = repository_over(rows).collaboration_network(
        {}, scope=scope, min_weight=1, limit=100
    )

    assert {node["type"] for node in result["nodes"]} == {scope}
    assert result["summary"]["node_count"] == 3
    # Beta sits between Alpha and Gamma in all three scopes.
    betweenness = {n["label"]: n["betweenness_centrality"] for n in result["nodes"]}
    assert betweenness["Beta"] > betweenness["Alpha"]
