"""Tests for situation viewer endpoint."""

import pytest
from fastapi.testclient import TestClient
from forgemind.api import create_api, situation_cache


def setup_function():
    """Clear cache before each test."""
    situation_cache.clear()


def test_view_cached_situation():
    """Test viewing a cached webhook situation."""
    result = {
        "status": "ok",
        "situation_id": "SIT-GITHUB-TEST",
        "m3_proof": {
            "provenance_links": {
                "event_id": "EVT-999",
                "coverage_plan_id": "CP-999",
                "execution_trace_id": "TRACE-999",
                "situation_id": "SIT-GITHUB-TEST",
                "artifact_chain": [],
            },
            "human_control_state": {"autonomy_class": "human_review", "state": "escalated"},
            "validation_verdict": {"state": "human_review"},
            "uncertainty_summary": {"confidence": 0.75},
        },
        "artifacts": {
            "coverage_plan": {"selected_domains": ["code"]},
            "evidence_shards": [],
            "domain_findings": [],
            "validated_situation": {},
        },
    }
    situation_cache.put("SIT-GITHUB-TEST", result)
    
    client = TestClient(create_api())
    response = client.get("/view/SIT-GITHUB-TEST")
    
    assert response.status_code == 200
    assert b"SIT-GITHUB-TEST" in response.content
    assert b"human_review" in response.content


def test_view_unknown_situation():
    """Test viewing unknown situation returns 404."""
    client = TestClient(create_api())
    response = client.get("/view/SIT-UNKNOWN")
    
    assert response.status_code == 404


def test_root_url_shows_default():
    """Test root URL shows default fixture."""
    client = TestClient(create_api())
    response = client.get("/")
    
    assert response.status_code == 200
    assert b"ForgeMind" in response.content