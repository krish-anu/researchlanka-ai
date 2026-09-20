"""Shared fixtures for Master Test Plan SW Testing suite."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from src.api.service import ResearchLankaAPI
from tests.support.env_loader import env_str, load_test_env
from tests.support.real_dataset import (
    RealPublicationRepository,
    dataset_path,
    load_real_publications,
)
from tests.phase3.helpers import make_api


@pytest.fixture(scope="session", autouse=True)
def _load_env() -> None:
    load_test_env()


@pytest.fixture(scope="session")
def real_repo() -> RealPublicationRepository:
    return RealPublicationRepository()


@pytest.fixture
def api(real_repo) -> ResearchLankaAPI:
    return ResearchLankaAPI(real_repo)


@pytest.fixture(scope="session")
def sample_publications():
    return list(load_real_publications(limit=32))


@pytest.fixture(scope="session")
def csv_path() -> Path:
    path = dataset_path()
    assert path.exists(), f"Processed common dataset missing: {path}"
    return path


@pytest.fixture
def database_url() -> str | None:
    load_test_env()
    return env_str("DATABASE_URL", "RESEARCHLANKA_DATABASE_URL")
