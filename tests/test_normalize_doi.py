"""Tests for DOI normalization and comparison."""

from src.quality.compare_dois import normalize_doi


def test_normalize_doi_url_with_dx():
    """Test DOI normalization from dx.doi.org URL."""
    doi = "https://dx.doi.org/10.1234/example.test"
    result = normalize_doi(doi)
    assert result == "10.1234/example.test"


def test_normalize_doi_url_without_dx():
    """Test DOI normalization from doi.org URL."""
    doi = "https://doi.org/10.5555/12345678"
    result = normalize_doi(doi)
    assert result == "10.5555/12345678"


def test_normalize_doi_http():
    """Test DOI normalization from http URL."""
    doi = "http://doi.org/10.1234/test"
    result = normalize_doi(doi)
    assert result == "10.1234/test"


def test_normalize_doi_with_prefix():
    """Test DOI normalization with DOI: prefix."""
    doi = "DOI: 10.1234/test"
    result = normalize_doi(doi)
    assert result == "10.1234/test"


def test_normalize_doi_case_insensitive():
    """Test DOI normalization is case-insensitive."""
    doi = "10.1234/TEST"
    result = normalize_doi(doi)
    assert result == "10.1234/test"


def test_normalize_doi_mixed_case_prefix():
    """Test DOI: prefix with mixed case."""
    doi = "Doi: 10.1234/Example"
    result = normalize_doi(doi)
    assert result == "10.1234/example"


def test_normalize_doi_whitespace():
    """Test DOI normalization with whitespace."""
    doi = "  10.1234/test  "
    result = normalize_doi(doi)
    assert result == "10.1234/test"


def test_normalize_doi_complex_example():
    """Test complex DOI normalization."""
    doi = "HTTPS://DX.DOI.ORG/10.1371/JOURNAL.PONE.0123456"
    result = normalize_doi(doi)
    assert result == "10.1371/journal.pone.0123456"


def test_normalize_doi_none():
    """Test DOI normalization with None."""
    result = normalize_doi(None)
    assert result is None


def test_normalize_doi_nan():
    """Test DOI normalization with NaN (float)."""
    result = normalize_doi(float("nan"))
    assert result is None


def test_normalize_doi_plain_doi():
    """Test DOI normalization with plain DOI."""
    doi = "10.1234/example.test"
    result = normalize_doi(doi)
    assert result == "10.1234/example.test"
