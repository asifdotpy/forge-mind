"""Contract tests for Webhook Payload Enrichment (ADR-011 / Pre-Demo Fix).

Tests the asynchronous payload enrichment layer that equips Tier-3 specialist
workers with real-world evidence from GitHub APIs (files, check runs, statuses).

Verifies:
1. High-evidence clean PRs reach `safe_autonomous`.
2. Failing CI PRs produce `human_review` or `escalate`.
3. Dependency changes trigger structured security scan signals.
4. Offline / network error fallbacks degrade gracefully without raising.
5. In-memory (repo, sha) caching and cache invalidation.
6. End-to-end FastAPI webhook endpoint behavior.
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from forgemind.api import create_api
from forgemind.enrichment import (
    clear_enrichment_cache,
    enrich_payload,
)
from forgemind.adk_runtime import run_adk_pipeline
from forgemind.api.models import EventInput


@pytest.fixture(autouse=True)
def clean_cache():
    """Ensure a clean enrichment cache before and after every test."""
    clear_enrichment_cache()
    yield
    clear_enrichment_cache()


class MockGitHubClient:
    """Mock GitHub client returning configurable API responses."""

    def __init__(
        self,
        files: list | None = None,
        check_runs: list | None = None,
        commit_status: dict | None = None,
        advisories: list | None = None,
        file_contents: dict | None = None,
        raise_on_files: bool = False,
        raise_on_check_runs: bool = False,
        raise_on_status: bool = False,
        raise_on_advisories: bool = False,
    ):
        self.files = files if files is not None else [
            {"filename": "README.md"},
            {"filename": "docs/architecture.md"},
        ]
        self.check_runs = check_runs if check_runs is not None else [
            {"name": "build", "status": "completed", "conclusion": "success"},
            {"name": "test", "status": "completed", "conclusion": "success"},
        ]
        self.commit_status = commit_status or {"state": "success"}
        self.advisories = advisories if advisories is not None else []
        self.file_contents = file_contents or {}
        self.raise_on_files = raise_on_files
        self.raise_on_check_runs = raise_on_check_runs
        self.raise_on_status = raise_on_status
        self.raise_on_advisories = raise_on_advisories
        self.calls = []

    def get(self, path: str, **kwargs):
        self.calls.append(path)
        if "files" in path:
            if self.raise_on_files:
                raise RuntimeError("GitHub API network error on files")
            return self.files
        if "check-runs" in path:
            if self.raise_on_check_runs:
                raise RuntimeError("GitHub API network error on check-runs")
            return {"check_runs": self.check_runs}
        if "status" in path:
            if self.raise_on_status:
                raise RuntimeError("GitHub API network error on status")
            return self.commit_status
        if "advisories" in path:
            if self.raise_on_advisories:
                raise RuntimeError("GitHub Advisory API error")
            return self.advisories
        if "contents" in path:
            for fname, c in self.file_contents.items():
                if fname in path:
                    import base64
                    return {"content": base64.b64encode(c.encode()).decode()}
            return {}
        return {}


def test_enrich_payload_clean_pr_produces_all_worker_signals():
    """Clean PR with green CI and doc changes populates all payload keys."""
    client = MockGitHubClient(
        files=[
            {"filename": "README.md"},
            {"filename": "docs/guide.md"},
            {"filename": "package.json"},
        ],
        check_runs=[
            {"name": "test", "status": "completed", "conclusion": "success"}
        ],
    )

    payload = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=101,
            sha="abc1234",
            client=client,
            use_cache=False,
        )
    )

    assert payload["repo"] == "thevertexagents/vertex-sentinel"
    assert payload["pr_number"] == 101
    assert payload["sha"] == "abc1234"
    assert "package.json" in payload["changed_files"]
    assert payload["ci_outcome"] == "pass"
    assert "documentation updated" in payload["docs_summary"]
    assert len(payload["dependency_scan"]) >= 1
    assert any("clean" in s or "0 known" in s for s in payload["dependency_scan"])
    assert payload["affected_domains"] == ["code", "delivery", "production"]


def test_enriched_payload_reaches_safe_autonomous():
    """An enriched payload with green CI and clean docs reaches safe_autonomous."""
    client = MockGitHubClient(
        files=[
            {"filename": "README.md"},
            {"filename": "docs/guide.md"},
        ],
        check_runs=[
            {"name": "test", "status": "completed", "conclusion": "success"}
        ],
    )

    payload = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=101,
            sha="abc1234",
            client=client,
        )
    )

    event = {
        "event_id": "EVT-TEST-101",
        "situation_id": "SIT-TEST-101",
        "timestamp": "2026-08-28T12:00:00Z",
        "source": "github",
        "type": "pr",
        "summary": "Docs update PR",
        "reference": "https://github.com/thevertexagents/vertex-sentinel/pull/101",
        "affected_entities": ["thevertexagents/vertex-sentinel"],
        "provenance": {"source_system": "github", "sender": "developer"},
        "selected_domains": ["code", "delivery", "production"],
        "selected_workers": [
            "pr-pre-flight-ast-worker",
            "docs-drift-and-spec-worker",
            "build-log-and-flakiness-worker",
            "alert-storm-clustering-worker",
            "telemetry-correlation-worker",
            "security-and-dependency-worker",
        ],
        "require_human_above_risk_level": "critical",
        "max_concurrent_managers": 3,
        "global_timeout_seconds": 300,
        "payload": payload,
    }

    result = run_adk_pipeline(EventInput(event=event))
    m3 = result.get("m3_proof", {})
    control = m3.get("human_control_state", {})

    assert result["status"] == "ok"
    assert control.get("autonomy_class") == "safe_autonomous"
    assert control.get("state") == "automated"
    assert result["terminal"]["type"] == "action"


def test_enrich_payload_failing_ci_triggers_human_review_or_escalation():
    """Failing CI outcome forces decision below autonomous threshold."""
    client = MockGitHubClient(
        files=[{"filename": "src/core.py"}],
        check_runs=[
            {"name": "pytest", "status": "completed", "conclusion": "failure"}
        ],
    )

    payload = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=102,
            sha="fail1234",
            client=client,
        )
    )

    assert payload["ci_outcome"] == "fail"

    event = {
        "event_id": "EVT-TEST-102",
        "situation_id": "SIT-TEST-102",
        "timestamp": "2026-08-28T12:00:00Z",
        "source": "github",
        "type": "pr",
        "summary": "Broken test PR",
        "reference": "https://github.com/thevertexagents/vertex-sentinel/pull/102",
        "affected_entities": ["thevertexagents/vertex-sentinel"],
        "provenance": {"source_system": "github", "sender": "developer"},
        "selected_domains": ["code", "delivery", "production"],
        "selected_workers": [
            "pr-pre-flight-ast-worker",
            "docs-drift-and-spec-worker",
            "build-log-and-flakiness-worker",
            "alert-storm-clustering-worker",
            "telemetry-correlation-worker",
            "security-and-dependency-worker",
        ],
        "require_human_above_risk_level": "critical",
        "max_concurrent_managers": 3,
        "global_timeout_seconds": 300,
        "payload": payload,
    }

    result = run_adk_pipeline(EventInput(event=event))
    m3 = result.get("m3_proof", {})
    control = m3.get("human_control_state", {})

    # Failing CI must NEVER be safe_autonomous
    assert control.get("autonomy_class") != "safe_autonomous"
    assert control.get("autonomy_class") in ("human_review", "escalate")


def test_enrich_payload_dependency_manifest_change():
    """Dependency files (e.g. package.json) are flagged in dependency_scan."""
    client = MockGitHubClient(
        files=[
            {"filename": "package.json"},
            {"filename": "src/index.js"},
        ],
        check_runs=[
            {"name": "test", "status": "completed", "conclusion": "success"}
        ],
    )

    payload = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=103,
            sha="dep1234",
            client=client,
        )
    )

    assert "package.json" in payload["changed_files"]
    assert any("clean" in s or "0 known" in s or "package.json" in s for s in payload["dependency_scan"])


def test_enrich_payload_advisory_detects_ghsa_vulnerability():
    """Vulnerability detected in GitHub Advisory DB triggers security findings and prevents autonomy."""
    client = MockGitHubClient(
        files=[{"filename": "package.json"}],
        file_contents={"package.json": '{"dependencies": {"vulnerable-pkg": "^1.0.0"}}'},
        advisories=[
            {
                "ghsa_id": "GHSA-xxxx-yyyy",
                "summary": "Remote code execution in vulnerable-pkg",
                "severity": "critical",
            }
        ],
        check_runs=[{"name": "test", "status": "completed", "conclusion": "success"}],
    )

    payload = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=106,
            sha="vuln123",
            client=client,
            use_cache=False,
        )
    )

    assert any("GHSA-xxxx-yyyy" in s for s in payload["dependency_scan"])

    event = {
        "event_id": "EVT-TEST-106",
        "situation_id": "SIT-TEST-106",
        "timestamp": "2026-08-28T12:00:00Z",
        "source": "github",
        "type": "pr",
        "summary": "Vulnerable dependency PR",
        "reference": "https://github.com/thevertexagents/vertex-sentinel/pull/106",
        "affected_entities": ["thevertexagents/vertex-sentinel"],
        "provenance": {"source_system": "github", "sender": "developer"},
        "selected_domains": ["code", "delivery", "production"],
        "selected_workers": [
            "pr-pre-flight-ast-worker",
            "docs-drift-and-spec-worker",
            "build-log-and-flakiness-worker",
            "alert-storm-clustering-worker",
            "telemetry-correlation-worker",
            "security-and-dependency-worker",
        ],
        "require_human_above_risk_level": "critical",
        "max_concurrent_managers": 3,
        "global_timeout_seconds": 300,
        "payload": payload,
    }

    result = run_adk_pipeline(EventInput(event=event))
    m3 = result.get("m3_proof", {})
    control = m3.get("human_control_state", {})

    # Critical security advisory must NEVER be safe_autonomous
    assert control.get("autonomy_class") != "safe_autonomous"
    assert control.get("autonomy_class") in ("human_review", "escalate")


def test_enrich_payload_gitbook_site_verification():
    """When GitBook API key is provided, site is queried and doc sync is confirmed."""
    client = MockGitHubClient(files=[{"filename": "src/api.py"}])

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {"items": [{"title": "API Specification"}]}

    with patch("requests.get", return_value=mock_resp):
        payload = asyncio.run(
            enrich_payload(
                repo="thevertexagents/vertex-sentinel",
                pr_number=107,
                sha="gb123",
                client=client,
                gitbook_api_key="gb_test_key",
                gitbook_organization_id="org_test",
                gitbook_site_id="site_test",
                use_cache=False,
            )
        )

    assert "GitBook site site_test" in payload["docs_summary"]


def test_enrich_payload_no_docs_no_deps_produces_honest_no_signal():
    """PR touching only code without doc changes or deps produces honest empty signals."""
    client = MockGitHubClient(files=[{"filename": "src/algo.py"}])

    payload = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=108,
            sha="codeonly123",
            client=client,
            use_cache=False,
        )
    )

    assert payload["changed_files"] == ["src/algo.py"]
    assert payload["docs_summary"] == ""
    assert payload["dependency_scan"] == []


def test_enrich_payload_offline_fallback_degrades_gracefully():
    """Network failure or unset credentials gracefully falls back to empty/unknown signals."""
    client = MockGitHubClient(raise_on_files=True, raise_on_check_runs=True, raise_on_status=True)

    payload = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=104,
            sha="err1234",
            client=client,
            use_cache=False,
        )
    )

    assert payload["changed_files"] == []
    assert payload["ci_outcome"] == "unknown"
    assert payload["docs_summary"] == ""
    assert payload["dependency_scan"] == []
    assert payload["affected_domains"] == ["code", "delivery", "production"]


def test_enrichment_caching_and_invalidation():
    """Cached payloads are reused within TTL and flushed by clear_enrichment_cache()."""
    client = MockGitHubClient(
        files=[{"filename": "cached.py"}],
        check_runs=[{"name": "ci", "status": "completed", "conclusion": "success"}],
    )

    p1 = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=105,
            sha="cache123",
            client=client,
            use_cache=True,
        )
    )
    assert len(client.calls) >= 2  # files + check-runs

    # Second call with same (repo, sha) should use cache (no new API calls)
    client.calls.clear()
    p2 = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=105,
            sha="cache123",
            client=client,
            use_cache=True,
        )
    )
    assert len(client.calls) == 0
    assert p1 == p2

    # Clear cache and verify re-fetch
    clear_enrichment_cache()
    p3 = asyncio.run(
        enrich_payload(
            repo="thevertexagents/vertex-sentinel",
            pr_number=105,
            sha="cache123",
            client=client,
            use_cache=True,
        )
    )
    assert len(client.calls) >= 2


def test_fastapi_webhook_e2e_with_enrichment():
    """The webhook endpoint /api/v1/adk/webhook runs enriched pipeline end-to-end."""
    app = create_api()
    client = TestClient(app)

    # 1. Ping event
    ping_resp = client.post("/api/v1/adk/webhook", json={"zen": "Non-blocking is better"})
    assert ping_resp.status_code == 200
    assert ping_resp.json() == {"status": "pong"}

    # 2. Mock GitHub tools to test webhook flow
    with patch("forgemind.enrichment._get_client") as mock_client_factory, \
         patch("forgemind.tools.github_tools.post_comment") as mock_comment, \
         patch("forgemind.tools.github_tools.update_status_check") as mock_status:

        mock_gh = MockGitHubClient(
            files=[{"filename": "README.md"}, {"filename": "docs/overview.md"}],
            check_runs=[{"name": "build", "status": "completed", "conclusion": "success"}],
        )
        mock_client_factory.return_value = mock_gh
        mock_comment.return_value = {"id": 12345, "body": "posted"}
        mock_status.return_value = {"id": 67890, "state": "success"}

        webhook_body = {
            "action": "opened",
            "repository": {"full_name": "thevertexagents/vertex-sentinel"},
            "sender": {"login": "octocat"},
            "pull_request": {
                "number": 205,
                "title": "Update Documentation",
                "html_url": "https://github.com/thevertexagents/vertex-sentinel/pull/205",
                "created_at": "2026-08-28T12:00:00Z",
                "head": {"sha": "999888777"},
            },
        }

        resp = client.post("/api/v1/adk/webhook", json=webhook_body)
        assert resp.status_code == 200
        data = resp.json()

        assert data.get("status") == "ok"
        assert data.get("agent") == "forgemind_hierarchical_dag"
        autonomy = data.get("autonomy", {})
        assert autonomy.get("autonomy_class") == "safe_autonomous"
        assert "analysis_comment_posted" in data.get("actions_taken", [])
        assert "status_check_passed" in data.get("actions_taken", [])
        assert "actions_result" in data
