"""Tests for ADK 2 monitoring search."""

import sys
import pytest
from unittest.mock import patch

from forgemind.monitoring_search import (
    MonitoringSearchService,
    clear_monitoring_cache,
    _MONITORING_CACHE,
)


class _FakePart:
    """Minimal stand-in for google.genai types.Part (text only)."""

    def __init__(self, text):
        self.text = text


class _FakeContent:
    """Minimal stand-in for google.genai types.Content."""

    def __init__(self, text):
        self.parts = [_FakePart(text)]


class _FakeSessionService:
    """Minimal stand-in for google.adk InMemorySessionService."""

    async def create_session(self, **kwargs):
        return None


class _FakeEvent:
    """Minimal stand-in for an ADK runner event."""

    def __init__(self, text):
        self._text = text

    def is_final_response(self):
        return True

    @property
    def content(self):
        return _FakeContent(self._text)


class _FakeRunner:
    """Minimal stand-in for google.adk Runner; yields one final event."""

    def __init__(self, text):
        self._text = text

    def run_async(self, **kwargs):
        async def _gen():
            yield _FakeEvent(self._text)

        return _gen()


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
    """Test the MonitoringSearchService status channel (ADR-013).

    Honesty contract: a real, successful query returns ``state="ok"`` even
    when the result set is empty; any failure (ADK not installed, unset
    credentials, query error) returns ``state="unavailable"`` with empty
    lists.  Callers must be able to distinguish "looked, was clean" from
    "could not be assessed".
    """

    def setup_method(self):
        clear_monitoring_cache()

    def test_search_incidents_no_adk_reports_unavailable(self):
        """ADK not installed -> state='unavailable' (never fail-open empty)."""
        service = MonitoringSearchService()
        with patch.dict(sys.modules, {"google.adk.agents": None}):
            result = service.search_incidents("test/repo")
        assert result["state"] == "unavailable"
        assert result["alerts"] == []
        assert result["telemetry"] == []

    def test_search_incidents_query_error_reports_unavailable(self):
        """A query error (auth failure, runtime error) -> state='unavailable'."""
        service = MonitoringSearchService()
        with patch("google.adk.agents.Agent", side_effect=RuntimeError("401")):
            result = service.search_incidents("test/repo")
        assert result["state"] == "unavailable"
        assert result["alerts"] == []
        assert result["telemetry"] == []

    def test_search_incidents_success_is_ok_even_when_empty(self):
        """A real query with zero results is state='ok' (looked, was clean)."""
        service = MonitoringSearchService()
        runner = _FakeRunner('{"alerts": [], "telemetry": []}')
        with (
            patch("google.adk.agents.Agent", lambda **kw: object()),
            patch("google.adk.runners.Runner", lambda **kw: runner),
            patch(
                "google.adk.sessions.InMemorySessionService",
                _FakeSessionService,
            ),
        ):
            result = service.search_incidents("test/repo")

        assert result["state"] == "ok"
        assert result["alerts"] == []
        assert result["telemetry"] == []

    def test_search_incidents_success_parses_findings(self):
        """A real query with findings parses them and reports state='ok'."""
        service = MonitoringSearchService()
        runner = _FakeRunner(
            '{"alerts": ["API latency SLO breach"], "telemetry": [0.42]}'
        )
        with (
            patch("google.adk.agents.Agent", lambda **kw: object()),
            patch("google.adk.runners.Runner", lambda **kw: runner),
            patch(
                "google.adk.sessions.InMemorySessionService",
                _FakeSessionService,
            ),
        ):
            result = service.search_incidents("test/repo")

        assert result["state"] == "ok"
        assert result["alerts"] == ["API latency SLO breach"]
        assert result["telemetry"] == [0.42]

    def test_search_incidents_non_json_prose_is_captured_as_alert(self):
        """Non-JSON final text mentioning incidents becomes an alert (state ok)."""
        service = MonitoringSearchService()
        runner = _FakeRunner("Active outage reported on the status page.")
        with (
            patch("google.adk.agents.Agent", lambda **kw: object()),
            patch("google.adk.runners.Runner", lambda **kw: runner),
            patch(
                "google.adk.sessions.InMemorySessionService",
                _FakeSessionService,
            ),
        ):
            result = service.search_incidents("test/repo")

        assert result["state"] == "ok"
        assert result["alerts"] == ["Active outage reported on the status page."]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
