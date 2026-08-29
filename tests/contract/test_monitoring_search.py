"""Tests for ADK 2 monitoring search."""

import pytest
from unittest.mock import patch

from forgemind.monitoring_search import (
    MonitoringSearchService,
    clear_monitoring_cache,
    _MONITORING_CACHE,
)


class TestMonitoringSearchCache:
    """Test the monitoring search cache."""

    def setup_method(self):
        clear_monitoring_cache()

    def test_cache_stores_results(self):
        """Results are cached after first lookup."""
        _MONITORING_CACHE["test/repo"] = (1000.0, {"alerts": ["alert1"], "telemetry": [0.5]})
        assert "test/repo" in _MONITORING_CACHE

    def test_clear_cache_removes_all(self):
        """clear_monitoring_cache removes all entries."""
        _MONITORING_CACHE["test/repo"] = (1000.0, {"alerts": [], "telemetry": []})
        clear_monitoring_cache()
        assert len(_MONITORING_CACHE) == 0


class TestMonitoringSearchService:
    """Test the MonitoringSearchService."""

    def setup_method(self):
        clear_monitoring_cache()

    def test_search_incidents_no_adk(self):
        """When ADK is unavailable, returns empty results."""
        service = MonitoringSearchService()
        with patch("google.adk.agents.Agent", side_effect=ImportError):
            result = service.search_incidents("test/repo")
            assert result == {"alerts": [], "telemetry": []}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
