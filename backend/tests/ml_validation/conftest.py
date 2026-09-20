"""Shared fixtures for ML validation tests."""

from __future__ import annotations

import pytest

from src.api.service import ResearchLankaAPI
from tests.support.env_loader import load_test_env
from tests.support.real_dataset import RealPublicationRepository


@pytest.fixture(scope="session", autouse=True)
def _load_env() -> None:
    load_test_env()


@pytest.fixture(scope="session")
def real_repo() -> RealPublicationRepository:
    return RealPublicationRepository()


@pytest.fixture
def api(real_repo) -> ResearchLankaAPI:
    return ResearchLankaAPI(real_repo)
