"""Thread-safe in-memory store for webhook-generated situations.

Stores the full event + result so situations can be retrieved
for the dashboard viewer and approval flow.

Risk: Memory grows unbounded. Mitigation: TTL + max size eviction.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, Optional

from forgemind.api.models import EventInput

__all__ = ["SituationStore"]


class SituationStore:
    """Thread-safe in-memory store for webhook-generated situations.

    Stores the full event + result so situations can be retrieved
    for the dashboard viewer and approval flow.

    Eviction policy:
    - Maximum 1000 situations (FIFO eviction)
    - 24-hour TTL per situation
    """

    _store: Dict[str, Dict[str, Any]] = {}
    _lock = threading.Lock()
    _max_size = 1000
    _ttl_seconds = 86400  # 24 hours

    @classmethod
    def save(cls, situation_id: str, event: Dict, result: Dict) -> None:
        """Store situation data.

        Args:
            situation_id: Unique situation identifier.
            event: The event dict that triggered the situation.
            result: The pipeline result dict.
        """
        with cls._lock:
            cls._evict_expired()
            cls._evict_overflow()

            cls._store[situation_id] = {
                "event": event,
                "result": result,
                "stored_at": time.time(),
            }

    @classmethod
    def get(cls, situation_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve situation data.

        Args:
            situation_id: Unique situation identifier.

        Returns:
            Dict with event, result, stored_at. None if not found or expired.
        """
        with cls._lock:
            data = cls._store.get(situation_id)
            if data is None:
                return None

            # Check TTL
            if time.time() - data["stored_at"] > cls._ttl_seconds:
                del cls._store[situation_id]
                return None

            return data

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
            cls._store.clear()

    @classmethod
    def count(cls) -> int:
        """Get count of stored situations.

        Returns:
            Number of stored situations.
        """
        with cls._lock:
            cls._evict_expired()
            return len(cls._store)

    @classmethod
    def _evict_expired(cls) -> None:
        """Remove expired situations."""
        now = time.time()
        expired = [
            k for k, v in cls._store.items()
            if now - v["stored_at"] > cls._ttl_seconds
        ]
        for k in expired:
            del cls._store[k]

    @classmethod
    def _evict_overflow(cls) -> None:
        """Remove oldest situations if over max size."""
        while len(cls._store) >= cls._max_size:
            oldest_key = min(cls._store, key=lambda k: cls._store[k]["stored_at"])
            del cls._store[oldest_key]
