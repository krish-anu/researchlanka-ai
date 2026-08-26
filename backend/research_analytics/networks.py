"""Collaboration network builders for publication records."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import Counter, defaultdict
from itertools import combinations
from typing import Any


AUTHOR_COLLABORATION_EDGE_TYPE = "author_collaboration"


def build_author_collaboration_network(
    records: list[dict[str, Any]],
    *,
    min_weight: int = 1,
    limit: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build a weighted coauthor graph from publication records.

    Nodes are authors/researchers and an edge means two authors appear on the
    same publication. When disambiguated ``author_ids`` are present and align
    positionally with ``authors``, those identifiers become node IDs; otherwise
    the graph falls back to stable IDs derived from display names.
    """

    min_weight = max(1, min_weight)
    edge_weights: Counter[tuple[str, str]] = Counter()
    node_labels: dict[str, str] = {}
    node_publications: Counter[str] = Counter()
    node_years: dict[str, set[int]] = defaultdict(set)
    edge_years: dict[tuple[str, str], set[int]] = defaultdict(set)

    for record in records:
        authors = _record_author_nodes(record)
        if not authors:
            continue

        publication_year = _publication_year(record)
        publication_seen: set[str] = set()
        for author_id, label in authors:
            if author_id in publication_seen:
                continue
            publication_seen.add(author_id)
            node_labels.setdefault(author_id, label)
            node_publications[author_id] += 1
            if publication_year is not None:
                node_years[author_id].add(publication_year)

        for left, right in combinations(publication_seen, 2):
            edge_key = tuple(sorted((left, right)))
            edge_weights[edge_key] += 1
            if publication_year is not None:
                edge_years[edge_key].add(publication_year)

    edges = [
        _edge_row(edge_key, weight, node_labels=node_labels, years=edge_years[edge_key])
        for edge_key, weight in edge_weights.items()
        if weight >= min_weight
    ]
    edges.sort(
        key=lambda row: (
            -int(row["weight"]),
            str(row["source_label"]).casefold(),
            str(row["target_label"]).casefold(),
        )
    )
    if limit is not None:
        edges = edges[: max(0, limit)]

    connected_node_ids = {
        node_id for edge in edges for node_id in (str(edge["source"]), str(edge["target"]))
    }
    nodes = [
        _node_row(
            author_id,
            node_labels[author_id],
            publication_count=node_publications[author_id],
            years=node_years[author_id],
        )
        for author_id in connected_node_ids
    ]
    nodes.sort(
        key=lambda row: (
            -int(row["publication_count"]),
            str(row["label"]).casefold(),
        )
    )

    return {"nodes": nodes, "edges": edges}


def split_author_values(value: Any) -> list[str]:
    """Split author-like multi-value fields without splitting surname commas."""

    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(split_author_values(item))
        return values

    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "null"}:
        return []

    parsed = _parse_list_literal(text)
    if parsed is not text:
        return split_author_values(parsed)

    return [part.strip() for part in text.split(";") if part.strip()]


def _record_author_nodes(record: dict[str, Any]) -> list[tuple[str, str]]:
    names = split_author_values(record.get("authors"))
    author_ids = split_author_values(record.get("author_ids"))
    if names and author_ids and len(names) == len(author_ids):
        return [(author_ids[index], names[index]) for index in range(len(names))]
    return [(_author_name_id(name), name) for name in names]


def _edge_row(
    edge_key: tuple[str, str],
    weight: int,
    *,
    node_labels: dict[str, str],
    years: set[int],
) -> dict[str, Any]:
    source, target = edge_key
    return {
        "source": source,
        "target": target,
        "source_label": node_labels[source],
        "target_label": node_labels[target],
        "weight": weight,
        "edge_type": AUTHOR_COLLABORATION_EDGE_TYPE,
        "first_year": min(years) if years else None,
        "last_year": max(years) if years else None,
    }


def _node_row(
    author_id: str,
    label: str,
    *,
    publication_count: int,
    years: set[int],
) -> dict[str, Any]:
    return {
        "id": author_id,
        "label": label,
        "type": "researcher",
        "publication_count": publication_count,
        "first_year": min(years) if years else None,
        "last_year": max(years) if years else None,
    }


def _author_name_id(name: str) -> str:
    text = re.sub(r"[^0-9a-z]+", "-", name.casefold()).strip("-")
    if text:
        return text
    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]
    return f"author-{digest}"


def _publication_year(record: dict[str, Any]) -> int | None:
    value = record.get("publication_year")
    if value in (None, ""):
        return None
    try:
        year = int(float(str(value)))
    except ValueError:
        return None
    return year if 1500 <= year <= 2100 else None


def _parse_list_literal(text: str) -> Any:
    if not text or text[0] not in "[(":
        return text
    for parser in (json.loads, ast.literal_eval):
        try:
            parsed = parser(text)
        except (json.JSONDecodeError, ValueError, SyntaxError):
            continue
        if isinstance(parsed, (list, tuple, set)):
            return parsed
    return text
