import pytest

from shared.config import get_settings
from shared.db import get_engine


@pytest.fixture(autouse=True)
def _clear_caches():
    get_engine.cache_clear()
    get_settings.cache_clear()
    yield
    get_engine.cache_clear()
    get_settings.cache_clear()


def test_get_engine_returns_same_instance(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/test")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("QUEUE_BACKEND", "sync")
    e1 = get_engine()
    e2 = get_engine()
    assert e1 is e2


def test_get_engine_uses_database_url_from_settings(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/mydb")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("QUEUE_BACKEND", "sync")
    engine = get_engine()
    assert "localhost" in str(engine.url)
    assert "mydb" in str(engine.url)


def test_get_engine_has_pool_pre_ping(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x:x@localhost/test")
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("QUEUE_BACKEND", "sync")
    engine = get_engine()
    assert engine.pool._pre_ping is True
