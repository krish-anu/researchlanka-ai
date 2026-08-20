"""Repository contracts used by the API service layer."""

from __future__ import annotations

from typing import Any, Protocol


class PublicationRepository(Protocol):
    """Storage operations required by the API service."""

    def health(self) -> bool:
        """Return whether the backing store is reachable."""

    def metadata(self) -> dict[str, Any]:
        """Return dataset metadata and counts."""

    def list_publications(
        self,
        filters: dict[str, Any],
        *,
        page: int,
        page_size: int,
        sort: str,
        include_facets: bool,
    ) -> dict[str, Any]:
        """Return publication rows, total count, and optional facet counts."""

    def get_publication(self, publication_key: str) -> dict[str, Any] | None:
        """Return one publication row."""

    def get_references(self, publication_key: str) -> list[dict[str, Any]]:
        """Return sidecar reference rows for a publication."""

    def get_count_audit(self, publication_key: str) -> dict[str, Any] | None:
        """Return count-audit sidecar evidence for a publication."""

    def suggest(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        """Return autocomplete suggestions."""

    def semantic_search(
        self,
        query: str,
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        """Return publications ranked by semantic similarity to query text."""

    def related_publications(
        self,
        publication_key: str,
        *,
        filters: dict[str, Any],
        limit: int,
        min_score: float | None,
    ) -> list[dict[str, Any]]:
        """Return publications ranked by semantic similarity to a publication."""

    def researcher_profile(self, researcher_key: str) -> dict[str, Any] | None:
        """Return an author/researcher aggregate."""

    def researcher_publications(
        self,
        researcher_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Return publications for an author/researcher."""

    def researcher_coauthors(self, researcher_key: str, *, limit: int) -> list[dict[str, Any]]:
        """Return coauthor aggregates."""

    def institution_profile(self, institution_key: str) -> dict[str, Any] | None:
        """Return an institution aggregate."""

    def institution_publications(
        self,
        institution_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Return publications for an institution."""

    def institution_collaborators(self, institution_key: str, *, limit: int) -> list[dict[str, Any]]:
        """Return collaborator aggregates for an institution."""

    def compare_institutions(self, institution_keys: list[str]) -> list[dict[str, Any]]:
        """Return headline metrics for selected institutions."""

    def topic_publications(
        self,
        topic_key: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Return publications for a topic."""

    def analytics_overview(self, filters: dict[str, Any]) -> dict[str, Any]:
        """Return national headline analytics."""

    def analytics_trends(self, filters: dict[str, Any], *, group_by: str, metric: str) -> list[dict[str, Any]]:
        """Return trend rows."""

    def analytics_rankings(
        self,
        filters: dict[str, Any],
        *,
        dimension: str,
        metric: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Return ranked aggregate rows."""

    def collaboration_network(
        self,
        filters: dict[str, Any],
        *,
        scope: str,
        min_weight: int,
        limit: int,
    ) -> dict[str, Any]:
        """Return graph nodes, edges, and a structural summary.

        Nodes carry centrality and community labels; the summary carries the
        graph-level context needed to read them (density, components,
        modularity). See :mod:`src.analytics.network`.
        """

    def data_quality(self, filters: dict[str, Any], *, group_by: str | None) -> dict[str, Any]:
        """Return data-quality metrics."""
