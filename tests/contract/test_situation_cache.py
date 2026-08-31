"""Tests for situation_cache module."""

import time
import pytest
from forgemind.api import situation_cache


def setup_function():
    """Clear cache before each test."""
    situation_cache.clear()


def test_put_and_get():
    """Test basic put/get operations."""
    result = {"status": "ok", "situation_id": "SIT-TEST-001"}
    situation_cache.put("SIT-TEST-001", result)
    
    assert situation_cache.get("SIT-TEST-001") == result
    assert situation_cache.exists("SIT-TEST-001") is True


def test_get_nonexistent():
    """Test getting non-existent situation."""
    assert situation_cache.get("SIT-NONEXISTENT") is None
    assert situation_cache.exists("SIT-NONEXISTENT") is False


def test_ttl_expiry():
    """Test that entries expire after TTL."""
    situation_cache.put("SIT-TEST", {"status": "ok"})
    
    # Manually set stored_at to past
    situation_cache._cache["SIT-TEST"]["stored_at"] = time.time() - situation_cache._TTL - 1
    
    assert situation_cache.get("SIT-TEST") is None


def test_overflow_eviction():
    """Test FIFO eviction when max size reached."""
    original_max = situation_cache._MAX_SIZE
    situation_cache._MAX_SIZE = 3
    
    situation_cache.put("SIT-1", {"id": 1})
    situation_cache.put("SIT-2", {"id": 2})
    situation_cache.put("SIT-3", {"id": 3})
    situation_cache.put("SIT-4", {"id": 4})  # Should evict SIT-1
    
    assert situation_cache.get("SIT-1") is None
    assert situation_cache.get("SIT-4") is not None
    assert situation_cache.count() == 3
    
    situation_cache._MAX_SIZE = original_max


def test_clear():
    """Test clearing all entries."""
    situation_cache.put("SIT-1", {"id": 1})
    situation_cache.put("SIT-2", {"id": 2})
    
    situation_cache.clear()
    
    assert situation_cache.count() == 0
    assert situation_cache.get("SIT-1") is None