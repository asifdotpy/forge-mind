"""Integration tests for webhook → cache → viewer flow."""

import pytest
from fastapi.testclient import TestClient
from forgemind.api import create_api, situation_cache


def setup_function():
    """Clear cache before each test."""
    situation_cache.clear()


def test_webhook_populates_cache():
    """Test that webhook processing populates the cache."""
    client = TestClient(create_api())
    
    # Simulate webhook
    response = client.post(
        "/api/v1/adk/webhook",
        json={
            "action": "opened",
            "number": 999,
            "pull_request": {
                "number": 999,
                "title": "Test PR",
                "created_at": "2026-08-30T10:00:00Z",
                "head": {"sha": "abc123"},
                "html_url": "https://github.com/test/repo/pull/999",
                "state": "open",
            },
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "testuser"},
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    situation_id = data.get("situation_id")
    
    assert situation_id is not None
    assert situation_cache.exists(situation_id) is True


def test_cached_situation_viewable():
    """Test that cached situation can be viewed."""
    client = TestClient(create_api())
    
    # Process webhook
    response = client.post(
        "/api/v1/adk/webhook",
        json={
            "action": "opened",
            "number": 999,
            "pull_request": {
                "number": 999,
                "title": "Test PR",
                "created_at": "2026-08-30T10:00:00Z",
                "head": {"sha": "abc123"},
                "html_url": "https://github.com/test/repo/pull/999",
                "state": "open",
            },
            "repository": {"full_name": "test/repo"},
            "sender": {"login": "testuser"},
        },
    )
    
    data = response.json()
    situation_id = data.get("situation_id")
    
    # View the situation
    view_response = client.get(f"/view/{situation_id}")
    
    assert view_response.status_code == 200
    assert situation_id.encode() in view_response.content