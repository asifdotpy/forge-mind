"""Tests for persistent SituationStore (SQLite backend + in-memory fallback).

Covers:
- Basic CRUD (save, get, exists, count, clear)
- Event retrieval (get_event)
- Persistence across simulated restarts
- Overwrite semantics
- TTL eviction
- FIFO overflow eviction
"""

from __future__ import annotations

import os
import tempfile
import time
from unittest import mock

import pytest

from forgemind.situation_store import SituationStore, _TTL_SECONDS, _MAX_SIZE


@pytest.fixture
def tmp_db(tmp_path):
    """Give each test an isolated SQLite database."""
    db_path = str(tmp_path / "situations.db")
    os.environ["FORGEMIND_SITUATION_DB"] = db_path
    SituationStore._use_memory = False
    SituationStore._db_ready = False
    yield db_path
    SituationStore.clear()


@pytest.fixture
def mem_store():
    """Give each test an isolated in-memory store."""
    SituationStore._use_memory = True
    SituationStore._mem_store.clear()
    yield
    SituationStore._mem_store.clear()


# =========================================================================
# In-memory tests (FORGEMIND_SITUATION_STORE=memory)
# =========================================================================
class TestInMemoryStore:
    def test_save_and_get(self, mem_store):
        SituationStore.save("SIT-1", {"type": "push"}, {"status": "ok"})
        data = SituationStore.get("SIT-1")
        assert data is not None
        assert data["event"] == {"type": "push"}
        assert data["result"] == {"status": "ok"}
        assert "stored_at" in data

    def test_get_not_found(self, mem_store):
        assert SituationStore.get("NOPE") is None

    def test_exists(self, mem_store):
        SituationStore.save("SIT-1", {}, {})
        assert SituationStore.exists("SIT-1") is True
        assert SituationStore.exists("NOPE") is False

    def test_count(self, mem_store):
        SituationStore.save("SIT-1", {}, {})
        SituationStore.save("SIT-2", {}, {})
        assert SituationStore.count() == 2

    def test_clear(self, mem_store):
        SituationStore.save("SIT-1", {}, {})
        SituationStore.clear()
        assert SituationStore.count() == 0

    def test_get_event(self, mem_store):
        SituationStore.save("SIT-1", {"type": "push", "repo": "x"}, {})
        ev = SituationStore.get_event("SIT-1")
        assert ev is not None
        assert ev.event["type"] == "push"

    def test_get_event_not_found(self, mem_store):
        assert SituationStore.get_event("NOPE") is None

    def test_ttl_eviction(self, mem_store):
        SituationStore.save("SIT-1", {}, {})
        # Force expiration by jumping time past TTL
        future = time.time() + _TTL_SECONDS + 1
        with mock.patch("forgemind.situation_store.time.time", return_value=future):
            assert SituationStore.get("SIT-1") is None
            assert SituationStore.count() == 0

    def test_fifo_eviction(self, mem_store):
        SituationStore._mem_store.clear()
        # Fill to capacity
        for i in range(_MAX_SIZE):
            SituationStore.save(f"SIT-{i}", {"i": i}, {})
        assert SituationStore.count() == _MAX_SIZE
        # Adding one more should evict the oldest
        SituationStore.save("SIT-NEW", {}, {})
        assert SituationStore.count() == _MAX_SIZE
        assert SituationStore.exists("SIT-NEW") is True

    def test_overwrite(self, mem_store):
        SituationStore.save("SIT-1", {"v": 1}, {"r": 1})
        SituationStore.save("SIT-1", {"v": 2}, {"r": 2})
        data = SituationStore.get("SIT-1")
        assert data["event"] == {"v": 2}
        assert data["result"] == {"r": 2}
        assert SituationStore.count() == 1


# =========================================================================
# SQLite tests
# =========================================================================
class TestSQLiteStore:
    def test_save_and_get(self, tmp_db):
        SituationStore.save("SIT-1", {"type": "push"}, {"status": "ok"})
        data = SituationStore.get("SIT-1")
        assert data is not None
        assert data["event"] == {"type": "push"}
        assert data["result"] == {"status": "ok"}

    def test_persistence_across_restart(self, tmp_db):
        SituationStore.save("SIT-1", {"type": "push"}, {"status": "ok"})
        # Simulate restart: reset connection state
        SituationStore._db_ready = False
        data = SituationStore.get("SIT-1")
        assert data is not None
        assert data["event"] == {"type": "push"}

    def test_count_and_clear(self, tmp_db):
        SituationStore.save("SIT-1", {}, {})
        SituationStore.save("SIT-2", {}, {})
        assert SituationStore.count() == 2
        SituationStore.clear()
        assert SituationStore.count() == 0

    def test_overwrite(self, tmp_db):
        SituationStore.save("SIT-1", {"v": 1}, {"r": 1})
        SituationStore.save("SIT-1", {"v": 2}, {"r": 2})
        data = SituationStore.get("SIT-1")
        assert data["event"] == {"v": 2}
        assert SituationStore.count() == 1

    def test_exists(self, tmp_db):
        SituationStore.save("SIT-1", {}, {})
        assert SituationStore.exists("SIT-1") is True
        assert SituationStore.exists("NOPE") is False

    def test_get_event(self, tmp_db):
        SituationStore.save("SIT-1", {"type": "push", "repo": "x"}, {})
        ev = SituationStore.get_event("SIT-1")
        assert ev is not None
        assert ev.event["type"] == "push"

    def test_ttl_eviction(self, tmp_db):
        SituationStore.save("SIT-1", {}, {})
        future = time.time() + _TTL_SECONDS + 1
        with mock.patch("forgemind.situation_store.time.time", return_value=future):
            assert SituationStore.get("SIT-1") is None
            assert SituationStore.count() == 0

    def test_fifo_eviction(self, tmp_db):
        for i in range(_MAX_SIZE):
            SituationStore.save(f"SIT-{i}", {"i": i}, {})
        assert SituationStore.count() == _MAX_SIZE
        SituationStore.save("SIT-NEW", {}, {})
        assert SituationStore.count() == _MAX_SIZE
        assert SituationStore.exists("SIT-NEW") is True

    def test_not_found(self, tmp_db):
        assert SituationStore.get("NOPE") is None
        assert SituationStore.get_event("NOPE") is None

    def test_db_file_created(self, tmp_db):
        SituationStore.save("SIT-1", {}, {})
        assert os.path.exists(tmp_db)