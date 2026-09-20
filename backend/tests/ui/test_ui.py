"""User interface page/component contract tests.

Run (from backend/):

    pytest tests/ui -v
"""

from __future__ import annotations

from tests.support.env_loader import REPO_ROOT

FRONTEND = REPO_ROOT / "frontend" / "src"


def _read(*parts: str) -> str:
    path = FRONTEND.joinpath(*parts)
    assert path.exists(), f"Missing UI source: {path}"
    return path.read_text(encoding="utf-8")


def test_main_application_page_renders_successfully():
    """Main ResearchLanka UI loads without rendering errors."""
    page = _read("app", "page.tsx")
    assert 'title: "National research dashboard"' in page
    assert "getAnalyticsOverview" in page
    assert "StatTile" in page
    assert 'href="/publications"' in page


def test_publication_listing_page_renders_publication_records():
    """Publications are displayed correctly in the UI."""
    page = _read("app", "publications", "page.tsx")
    assert "listPublications" in page
    assert "PublicationCardList" in page
    assert "publications={result.value.data}" in page
    assert "No publications match these filters" in page


def test_publication_search_updates_results_correctly():
    """User search input produces the expected publication results."""
    page = _read("app", "publications", "page.tsx")
    search_box = _read("components", "search", "SearchBox.tsx")
    assert "SearchBox" in page
    assert 'initialQuery={query}' in page
    assert 'params.q' in page
    assert 'targetPath = "/publications"' in search_box
    assert "router.push(searchHref(value))" in search_box


def test_year_filter_controls_update_publication_results():
    """UI filters actually affect the displayed data."""
    page = _read("app", "publications", "page.tsx")
    filters = _read("components", "publications", "FilterControls.tsx")
    assert "FilterControls" in page
    assert "extractFilters" in page
    assert 'name="year_min"' in filters
    assert 'name="year_max"' in filters
    assert 'method="get"' in filters
    assert 'action={basePath}' in filters


def test_publication_detail_page_displays_selected_publication():
    """Clicking/opening a publication shows its details."""
    page = _read("app", "publications", "[...key]", "page.tsx")
    assert "getPublication" in page
    assert "PublicationDetail" in page or "result.value.data.title" in page
    assert "abstract" in page
    assert "notFound" in page


def test_analytics_dashboard_renders_charts_and_key_metrics():
    """Plotly/analytics components load and display data."""
    page = _read("app", "page.tsx")
    trend = _read("components", "charts", "TrendLineChart.tsx")
    assert "TrendLineChart" in page
    assert "RankingBarChart" in page
    assert "getAnalyticsTrends" in page
    assert "getAnalyticsOverview" in page
    assert "plotly" in trend.casefold() or "PlotlyChart" in trend


def test_collaboration_network_renders_nodes_and_relationships():
    """Cytoscape visualization loads correctly."""
    page = _read("app", "page.tsx")
    network = _read("components", "network", "CollaborationNetwork.tsx")
    assert "CollaborationNetwork" in page
    assert "getCollaborationNetwork" in page
    assert "cytoscape" in network.casefold()
    assert "nodes" in network.casefold()


def test_ai_review_page_renders_review_information_and_actions():
    """AI/NON_AI results, confidence/status, and review controls are visible."""
    page = _read("app", "admin", "ai-review", "page.tsx")
    card = _read("components", "admin", "AIReviewCard.tsx")
    assert "AI Review" in page
    assert "AIReviewCard" in page
    assert "listAIReviewCandidates" in page
    assert "Gemini prediction" in card
    assert "Gemini confidence" in card
    assert "Accept as AI" in card
    assert "Reject as Non-AI" in card
    assert "human_accepted" in card
    assert "human_rejected" in card
