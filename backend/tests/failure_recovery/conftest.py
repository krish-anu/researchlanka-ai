"""Shared fixtures for failure and recovery tests."""

from __future__ import annotations

import pytest

from src.api.service import ResearchLankaAPI
from tests.support.env_loader import load_test_env
from tests.support.real_dataset import RealPublicationRepository, load_real_publications
from tests.phase3.helpers import make_api


@pytest.fixture(scope="session", autouse=True)
def _load_env() -> None:
    load_test_env()


@pytest.fixture(scope="session")
def sample_publications():
    return list(load_real_publications(limit=16))


@pytest.fixture
def api() -> ResearchLankaAPI:
    return make_api()


@pytest.fixture
def real_repo() -> RealPublicationRepository:
    return RealPublicationRepository()
