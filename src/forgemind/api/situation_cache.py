"""Shared in-memory cache for webhook-generated situations.

Stores the full pipeline result so the viewer can render the complete
dashboard without SQLite (which fails on Cloud Run's read-only filesystem).
"""

from threading import Lock
from typing import Any, Dict, Optional
import time

_cache: Dict[str, Dict[str, Any]] = {}
_lock = Lock()
_TTL = 86400  # 24 hours
_MAX_SIZE = 1000

def put(situation_id: str, result: Dict[str, Any]) -> None:
    """Store a pipeline result for the given situation_id."""
    with _lock:
        _evict_expired()
        _evict_overflow()
        _cache[situation_id] = {
            "result": result,
            "stored_at": time.time(),
        }

def get(situation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a cached result, or None if not found/expired."""
    with _lock:
        data = _cache.get(situation_id)
        if data is None:
            return None
        if time.time() - data["stored_at"] > _TTL:
            del _cache[situation_id]
            return None
        return data["result"]

def exists(situation_id: str) -> bool:
    """Check if a non-expired entry exists for situation_id."""
    return get(situation_id) is not None

def clear() -> None:
    """Clear all cached entries. For testing."""
    with _lock:
        _cache.clear()

def count() -> int:
    """Return the number of cached entries."""
    with _lock:
        return len(_cache)

def _evict_expired() -> None:
    """Remove expired entries from the cache."""
    cutoff = time.time() - _TTL
    expired = [k for k, v in _cache.items() if v["stored_at"] < cutoff]
    for k in expired:
        del _cache[k]

def _evict_overflow() -> None:
    """Evict oldest entries when cache exceeds max size."""
    while len(_cache) >= _MAX_SIZE:
        oldest = min(_cache, key=lambda k: _cache[k]["stored_at"])
        del _cache[oldest]