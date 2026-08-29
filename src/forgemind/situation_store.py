"""Persistent, thread-safe store for webhook-generated situations.

Stores the full event + result so situations can be retrieved
for the dashboard viewer and approval flow.

Storage backends
----------------
- **Persistent (default):** SQLite (``situations.db``). Survives restarts;
  works on Cloud Run ephemeral disk (data survives restarts but is lost
  when the container is replaced). Zero external dependencies — ideal for
  hackathon demos and local development.
- **In-memory:** Set ``FORGEMIND_SITUATION_STORE=memory`` for tests.

Migration
---------
Drop-in replacement for the previous in-memory-only implementation.
Public API is unchanged; no callers need to be modified.

Migration from the previous in-memory store
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
1. Replace ``situation_store.py`` with this file.
2. No code changes needed elsewhere — the public API is unchanged.
3. On first use, the SQLite file is created and the ``situations`` table
   is initialized automatically.

Ephemeral-disk caveat
~~~~~~~~~~~~~~~~~~~~~
On Cloud Run, data persists across restarts but is wiped when the
container is replaced (new revision, scaling to zero, etc.). For true
durability beyond container lifetime, see
https://cloud.google.com/run/docs/configuring/databases for Cloud SQL
or Firestore options. For the hackathon demo, SQLite is sufficient.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from typing import Any, Dict, Optional

from forgemind.api.models import EventInput

__all__ = ["SituationStore"]

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_TTL_SECONDS = 86400  # 24 hours
_MAX_SIZE = 1000  # FIFO eviction threshold

# Default SQLite path. Override with FORGEMIND_SITUATION_DB if needed.
_DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "situations.db"
)


class SituationStore:
    """Thread-safe, persistent store for webhook-generated situations.

    Public interface (unchanged from previous in-memory implementation):
        save(situation_id, event, result)
        get(situation_id) -> Optional[Dict]
        get_event(situation_id) -> Optional[EventInput]
        exists(situation_id) -> bool
        clear()
        count() -> int
    """

    # When True, use an in-memory dict (for tests).
    _use_memory: bool = os.environ.get("FORGEMIND_SITUATION_STORE", "") == "memory"

    _lock = threading.Lock()

    # ---------- in-memory fallback (tests) ----------
    _mem_store: Dict[str, Dict[str, Any]] = {}

    # ---------- SQLite setup ----------
    _db_path: Optional[str] = None  # resolved lazily
    _db_ready: bool = False

    @classmethod
    def _resolve_db_path(cls) -> str:
        """Resolve DB path from env or default. Called lazily so tests can set env vars before first use."""
        env_path = os.environ.get("FORGEMIND_SITUATION_DB")
        if env_path:
            return env_path
        return _DEFAULT_DB_PATH

    @classmethod
    def _db(cls) -> sqlite3.Connection:
        """Return a thread-local SQLite connection and ensure schema exists."""
        conn = sqlite3.connect(cls._resolve_db_path(), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        if not cls._db_ready:
            cls._init_schema(conn)
            cls._db_ready = True
        return conn

    @classmethod
    def _init_schema(cls, conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS situations (
                situation_id TEXT PRIMARY KEY,
                event        TEXT NOT NULL,
                result       TEXT NOT NULL,
                stored_at    REAL NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_situations_stored_at "
            "ON situations(stored_at)"
        )
        conn.commit()

    # ------------------------------------------------------------------
    # Eviction helpers
    # ------------------------------------------------------------------
    @classmethod
    def _evict_expired(cls, conn: sqlite3.Connection) -> None:
        cutoff = time.time() - _TTL_SECONDS
        conn.execute("DELETE FROM situations WHERE stored_at < ?", (cutoff,))

    @classmethod
    def _evict_overflow(cls, conn: sqlite3.Connection) -> None:
        # FIFO: delete oldest rows until we're under the cap.
        while True:
            cur = conn.execute("SELECT COUNT(*) AS n FROM situations")
            n = cur.fetchone()["n"]
            if n < _MAX_SIZE:
                break
            conn.execute(
                "DELETE FROM situations WHERE situation_id = ("
                "  SELECT situation_id FROM situations "
                "  ORDER BY stored_at ASC LIMIT 1)"
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @classmethod
    def save(cls, situation_id: str, event: Dict, result: Dict) -> None:
        """Store situation data.

        Args:
            situation_id: Unique situation identifier.
            event: The event dict that triggered the situation.
            result: The pipeline result dict.
        """
        with cls._lock:
            if cls._use_memory:
                cls._mem_evict_expired()
                cls._mem_evict_overflow()
                cls._mem_store[situation_id] = {
                    "event": event,
                    "result": result,
                    "stored_at": time.time(),
                }
                return

            conn = cls._db()
            try:
                cls._evict_expired(conn)
                cls._evict_overflow(conn)
                conn.execute(
                    """
                    INSERT INTO situations (situation_id, event, result, stored_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(situation_id) DO UPDATE SET
                        event = excluded.event,
                        result = excluded.result,
                        stored_at = excluded.stored_at
                    """,
                    (
                        situation_id,
                        json.dumps(event),
                        json.dumps(result),
                        time.time(),
                    ),
                )
                conn.commit()
            finally:
                conn.close()

    @classmethod
    def get(cls, situation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve situation data.

        Args:
            situation_id: Unique situation identifier.

        Returns:
            Dict with event, result, stored_at. None if not found or expired.
        """
        with cls._lock:
            if cls._use_memory:
                data = cls._mem_store.get(situation_id)
                if data is None:
                    return None
                if time.time() - data["stored_at"] > _TTL_SECONDS:
                    del cls._mem_store[situation_id]
                    return None
                return data

            conn = cls._db()
            try:
                row = conn.execute(
                    "SELECT event, result, stored_at FROM situations "
                    "WHERE situation_id = ?",
                    (situation_id,),
                ).fetchone()
                if row is None:
                    return None
                stored_at = row["stored_at"]
                if time.time() - stored_at > _TTL_SECONDS:
                    conn.execute(
                        "DELETE FROM situations WHERE situation_id = ?",
                        (situation_id,),
                    )
                    conn.commit()
                    return None
                return {
                    "event": json.loads(row["event"]),
                    "result": json.loads(row["result"]),
                    "stored_at": stored_at,
                }
            finally:
                conn.close()

    @classmethod
    def get_event(cls, situation_id: str) -> Optional[EventInput]:
        """Get event for re-deriving situation.

        Args:
            situation_id: Unique situation identifier.

        Returns:
            EventInput if found, None otherwise.
        """
        data = cls.get(situation_id)
        if data is None:
            return None
        return EventInput(event=data["event"])

    @classmethod
    def exists(cls, situation_id: str) -> bool:
        """Check if situation exists and is not expired.

        Args:
            situation_id: Unique situation identifier.

        Returns:
            True if situation exists and is valid.
        """
        return cls.get(situation_id) is not None

    @classmethod
    def clear(cls) -> None:
        """Clear all stored situations. For testing."""
        with cls._lock:
            if cls._use_memory:
                cls._mem_store.clear()
                return
            conn = cls._db()
            try:
                conn.execute("DELETE FROM situations")
                conn.commit()
            finally:
                conn.close()

    @classmethod
    def count(cls) -> int:
        """Get count of stored situations.

        Returns:
            Number of stored situations.
        """
        with cls._lock:
            if cls._use_memory:
                cls._mem_evict_expired()
                return len(cls._mem_store)
            conn = cls._db()
            try:
                cls._evict_expired(conn)
                conn.commit()
                row = conn.execute("SELECT COUNT(*) AS n FROM situations").fetchone()
                return row["n"]
            finally:
                conn.close()

    # ------------------------------------------------------------------
    # In-memory eviction helpers (for tests)
    # ------------------------------------------------------------------
    @classmethod
    def _mem_evict_expired(cls) -> None:
        now = time.time()
        expired = [
            k for k, v in cls._mem_store.items()
            if now - v["stored_at"] > _TTL_SECONDS
        ]
        for k in expired:
            del cls._mem_store[k]

    @classmethod
    def _mem_evict_overflow(cls) -> None:
        while len(cls._mem_store) >= _MAX_SIZE:
            oldest_key = min(
                cls._mem_store, key=lambda k: cls._mem_store[k]["stored_at"]
            )
            del cls._mem_store[oldest_key]