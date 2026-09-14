import sys
from types import SimpleNamespace

import pytest

from src.database.connection import (
    DEFAULT_DATABASE_URL,
    get_connection,
    get_database_url,
)


def test_get_database_url_uses_default_when_env_missing(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    assert get_database_url() == DEFAULT_DATABASE_URL


def test_postgres_connection_uses_psycopg(monkeypatch):
    calls = []
    fake_connection = object()

    def fake_connect(database_url):
        calls.append(database_url)
        return fake_connection

    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))

    connection = get_connection("postgresql://user:password@localhost:5432/dbname")

    assert connection is fake_connection
    assert calls == ["postgresql://user:password@localhost:5432/dbname"]


def test_connection_can_use_discrete_postgres_env_vars(monkeypatch):
    calls = []
    fake_connection = object()

    def fake_connect(**kwargs):
        calls.append(kwargs)
        return fake_connection

    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_HOST", "db")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "researchlanka")
    monkeypatch.setenv("POSTGRES_USER", "researchlanka_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "slash/safe+because/not/in/url")
    monkeypatch.setitem(sys.modules, "psycopg", SimpleNamespace(connect=fake_connect))

    connection = get_connection()

    assert connection is fake_connection
    assert calls == [
        {
            "host": "db",
            "port": 5432,
            "dbname": "researchlanka",
            "user": "researchlanka_user",
            "password": "slash/safe+because/not/in/url",
        }
    ]


def test_unsupported_database_url_raises_helpful_error():
    with pytest.raises(ValueError, match="Unsupported DATABASE_URL"):
        get_connection("mysql://user:password@localhost/researchlanka")
