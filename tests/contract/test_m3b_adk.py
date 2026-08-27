"""M3-B integration tests (T733) — bounded Gemini + ADK 2 workflow.

These tests exercise the M3-B additions WITHOUT asserting any model text:
they verify the fail-closed deterministic fallback, the ADK runtime import
surface, parity between the deterministic and ADK paths, the human-approval
pause/resume gate, and the ADR-009 ChromaDB boundary for the new modules.

The 133 baseline suite is unaffected: every M3-B behavior here is additive
and the deterministic path is byte-identical to ``api.run_pipeline``.
"""

import copy
import importlib
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PACKAGE_DIR = REPO_ROOT / "src" / "forgemind"
FIXTURES_INPUT_DIR = REPO_ROOT / "fixtures" / "inputs"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_INPUT_DIR / name).read_text(encoding="utf-8"))


def _event_input_for(fixture: dict, **overrides):
    from forgemind.api import EventInput

    payload = dict(fixture)
    payload.update(overrides)
    return EventInput(**payload)


def test_llm_adapter_falls_back_without_creds(monkeypatch):
    """generate_observations returns None with no creds (deterministic)."""
    for var in ("VERTEX_PROJECT", "GOOGLE_CLOUD_PROJECT", "GOOGLE_API_KEY"):
        monkeypatch.delenv(var, raising=False)

    from forgemind.llm.adapter import generate_observations

    out = generate_observations("code", {"inputs": {"changed_files": ["a.py"]}})
    assert out is None

    # The worker therefore keeps its deterministic observations unchanged.
    from forgemind.acquisition import acquire_event
    from forgemind.workers import PRPreFlightASTWorker

    fixture = _load_fixture("FIXTURE-001-happy-path.json")
    plan = acquire_event(fixture["event"])["coverage_plan"]
    ctx = {"domain": "code", "inputs": {"changed_files": ["src/auth.py"]}}
    shard = PRPreFlightASTWorker().build_shard(plan, ctx)
    assert shard["observations"] == ["changed file in changeset: src/auth.py"]
    assert shard["domain"] == "code"


def test_adk_runtime_imports():
    """import forgemind.adk_runtime works (lazy genai, offline-safe)."""
    importlib.import_module("forgemind.adk_runtime")
    from forgemind.adk_runtime import (
        describe_adk_workflow,
        is_adk_runtime,
        resume_adk_pipeline,
        run_adk_pipeline,
    )

    assert callable(run_adk_pipeline)
    assert callable(resume_adk_pipeline)
    assert callable(is_adk_runtime)
    # The ADK 2 node graph is explicit and ordered.
    nodes = describe_adk_workflow()
    assert nodes[0] == "acquire"
    assert "human_approval" in nodes
    assert nodes[-1] == "action_gate"


def test_adk_deterministic_path_matches():
    """ADK path == deterministic path on the NON-pausing (allowed) path.

    Parity is asserted on ``FIXTURE-007-m3-judge-surface-action.json``, whose
    verified multi-domain findings reach ``safe_autonomous`` / ``allowed`` and
    therefore do NOT hit the ADK human-approval PAUSE. Both runtimes publish
    the same terminal and must be byte-identical here.

    FIXTURE-001 is deliberately NOT used: since Change 1 it resolves to a
    ``human_review`` / ``requires_human`` outcome at confidence 0.7, which the
    ADK path PAUSES on by design while the deterministic path publishes the
    ``policy_boundary`` escalation — those two runtimes are correctly NOT
    identical on a pausing path. The pause/resume contract is asserted
    separately in ``test_adk_human_approval_pause_resume``.
    """
    from forgemind.adk_runtime import run_adk_pipeline
    from forgemind.api import EventInput, run_pipeline

    fixture = _load_fixture("FIXTURE-007-m3-judge-surface-action.json")
    body = EventInput(**fixture)

    expected = run_pipeline(body)
    actual = run_adk_pipeline(body)

    # Byte-identical artifacts + terminal for the non-pausing (allowed) path.
    assert expected == actual
    assert actual["status"] == "ok"
    # Parity: both runtimes land on the same autonomous terminal.
    assert actual["terminal"]["type"] == "action"
    assert (
        actual["terminal"]["action_validation"]["policy_result"] == "allowed"
    )


def test_human_approval_pauses():
    """A requires_human decision pauses; publishing needs explicit resume."""
    from forgemind.adk_runtime import resume_adk_pipeline, run_adk_pipeline

    # Build a requires_human body: take FIXTURE-007's findings, drop
    # confidence below the autonomous threshold and remove causal language so
    # causality becomes 'correlated' -> human_review -> requires_human.
    fixture = _load_fixture("FIXTURE-007-m3-judge-surface-action.json")
    findings = copy.deepcopy(fixture["domain_findings"])
    claim = "the auth-service error rate is elevated in staging"
    for f in findings:
        f["confidence"] = 0.6
        f["supported_claims"] = [claim]
        f["summary"] = "mutated to force a requires_human decision"

    body = _event_input_for(fixture, domain_findings=findings)

    # First pass PAUSES before publishing.
    paused = run_adk_pipeline(body)
    assert paused["status"] == "paused"
    assert paused["terminal"] is None
    token = paused["pending_approval"]["token"]
    assert paused["pending_approval"]["decision_required"] is True

    # Approve -> the gated outcome is published (escalation for requires_human).
    approved = resume_adk_pipeline(token, "approve")
    assert approved["human_decision"] == "approve"
    assert approved["terminal"]["type"] == "escalation"
    assert approved["terminal"]["escalation"]["reason"] == "policy_boundary"

    # A fresh pause + reject -> Escalation recorded, no action published.
    paused2 = run_adk_pipeline(body)
    rejected = resume_adk_pipeline(
        paused2["pending_approval"]["token"], "reject"
    )
    assert rejected["human_decision"] == "reject"
    assert rejected["terminal"]["type"] == "escalation"
    assert rejected["terminal"]["proposed_action"] is None
    assert "rejected" in rejected["terminal"]["escalation"]["summary"].lower()

    # Unknown token -> ApprovalError surfaces as a clean 404 upstream.
    with pytest.raises(Exception):
        resume_adk_pipeline("does-not-exist", "approve")


def test_no_chroma_in_runtime():
    """llm/adk_runtime never import chromadb (ADR-009 boundary)."""
    # 1) Source scan: no 'chroma' token in the new runtime modules.
    offenders = []
    for path in (SRC_PACKAGE_DIR / "llm").rglob("*.py"):
        if "chroma" in path.read_text(encoding="utf-8").lower():
            offenders.append(path.name)
    if "chroma" in (SRC_PACKAGE_DIR / "adk_runtime.py").read_text(
        encoding="utf-8"
    ).lower():
        offenders.append("adk_runtime.py")
    assert not offenders

    # 2) Import-block: importing both modules with chromadb hard-blocked
    #    must succeed (mirrors the ADR-009 boundary test).
    child_code = (
        "import importlib, sys\n"
        "class B:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'chromadb' or name.startswith('chromadb.'):\n"
        "            raise ImportError('BLOCKED ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, B())\n"
        "importlib.import_module('forgemind.llm')\n"
        "importlib.import_module('forgemind.llm.adapter')\n"
        "importlib.import_module('forgemind.adk_runtime')\n"
        "print('M3B_RUNTIME_OK')\n"
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")
    result = subprocess.run(
        [sys.executable, "-c", child_code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, (
        f"M3-B runtime modules failed to import with chromadb blocked: "
        f"{result.stdout} {result.stderr}"
    )
    assert "M3B_RUNTIME_OK" in result.stdout

def test_adk_events_runs_real_dag():
    """POST /api/v1/adk/events executes the hierarchical DAG, not a heuristic.

    Asserts the endpoint returns the authoritative artifacts + m3_proof and
    that the old Gemini-direct + ``changed_files``-count heuristic envelope
    (``analysis``) is gone.  Parity with ``run_adk_pipeline`` is enforced by
    comparing the terminal outcome on the action fixture.
    """
    from fastapi.testclient import TestClient

    from forgemind.adk_runtime import run_adk_pipeline
    from forgemind.api import create_api
    from forgemind.api.models import EventInput

    client = TestClient(create_api())

    fixture = _load_fixture("FIXTURE-007-m3-judge-surface-action.json")
    body = {
        "event": fixture["event"],
        "domain_findings": fixture.get("domain_findings"),
        "workers": fixture.get("workers"),
        "evidence_shards": fixture.get("evidence_shards"),
    }

    resp = client.post("/api/v1/adk/events", json=body)
    assert resp.status_code == 200
    d = resp.json()

    # Real hierarchical DAG output surfaces, not the old heuristic envelope.
    assert "analysis" not in d, "heuristic 'analysis' block must be removed"
    assert d["agent"] == "forgemind_hierarchical_dag"
    assert d["status"] == "ok"
    assert d["autonomy"]["autonomy_class"] == "safe_autonomous"
    assert d["actions_taken"] == [
        "analysis_comment_posted",
        "status_check_passed",
    ]
    assert d["terminal"]["type"] == "action"

    # Full trajectory lineage is preserved (Event -> ... -> Terminal chain).
    chain = d["m3_proof"]["provenance_links"]["artifact_chain"]
    assert len(chain) == 7
    assert chain[0]["artifact"] == "coverage_plan"
    assert chain[-1]["artifact"] == "terminal"

    # Parity with the underlying pipeline function for the same inputs.
    pipeline_result = run_adk_pipeline(
        EventInput(
            event=fixture["event"],
            domain_findings=fixture.get("domain_findings"),
            workers=fixture.get("workers"),
            evidence_shards=fixture.get("evidence_shards"),
        )
    )
    assert pipeline_result["terminal"]["type"] == "action"
    assert (
        d["terminal"]["type"],
        d["autonomy"]["autonomy_class"],
    ) == (
        pipeline_result["terminal"]["type"],
        pipeline_result["m3_proof"]["human_control_state"]["autonomy_class"],
    )


def test_webhook_executes_actions_token_missing():
    """Webhook surfaces a visible 'token not configured' instead of silent skip.

    With GITHUB_TOKEN unset, the DAG still runs and returns a paused/human
    outcome with no actions; for a safe_autonomous payload the dispatcher would
    attempt writes and report the missing token.  This guards the dispatch
    wiring (checks actions_taken, not just autonomy_class) against regressions.
    """
    from forgemind.api.adk_routes import _execute_github_actions

    # safe_autonomous result advertises both actions; without a token both
    # tools return the "not configured" error dict.
    result = {
        "actions_taken": [
            "analysis_comment_posted",
            "status_check_passed",
        ],
        "analysis_comment": "## ForgeMind Analysis",
    }
    event = {
        "payload": {
            "repo": "owner/test-repo",
            "pr_number": 7,
            "sha": "deadbeef",
        }
    }
    executed = _execute_github_actions(event, result)
    assert "analysis_comment_posted" in executed
    assert "status_check_passed" in executed
    for outcome in executed.values():
        assert isinstance(outcome, dict) and outcome.get("error")

    # human_review advertises only the comment action (status stays gated).
    result2 = {"actions_taken": ["analysis_comment_posted"], "analysis_comment": "x"}
    executed2 = _execute_github_actions(event, result2)
    assert "analysis_comment_posted" in executed2
    assert "status_check_passed" not in executed2


def test_adk_events_event_only_is_conservative():
    """A bare GitHub-PR event pauses (human_review), never auto-acts.

    The real reducer is conservative: without pre-computed evidence the
    validated confidence stays below the autonomous threshold, so the
    /adk/events response is ``paused`` with a resume token.  This guards
    against re-introducing the optimistic ``len(changed_files)`` heuristic.
    """
    from fastapi.testclient import TestClient

    from forgemind.api import create_api

    client = TestClient(create_api())

    event = {
        "event_id": "EVT-GUARD",
        "situation_id": "SIT-GUARD",
        "timestamp": "2026-08-27T10:00:00Z",
        "source": "github",
        "type": "pr",
        "summary": "docs update",
        "reference": "https://github.com/x/y/pull/1",
        "affected_entities": ["x/y"],
        "provenance": {"source_system": "github", "sender": "bot"},
        "selected_domains": ["code"],
        "selected_workers": ["pr-pre-flight-ast-worker"],
        "require_human_above_risk_level": "critical",
        "max_concurrent_managers": 3,
        "global_timeout_seconds": 300,
        "payload": {
            "changed_files": ["README.md"],
            "pr_number": 1,
            "repo": "x/y",
            "sha": "abc123",
        },
    }

    d = client.post("/api/v1/adk/events", json={"event": event}).json()
    assert d["status"] == "paused"
    assert d["terminal"] is None
    assert d["pending_approval"]["token"]
    # The bare event lands in human_review (conservative). With the paused
    # projection fix, the decision_record + action_validation supplied by
    # adk_runtime flow through m3_proof so the envelope surfaces the correct
    # autonomy signal and lists the comment action even though no terminal
    # has been published yet. Status checks stay gated (only safe_autonomous).
    assert d["autonomy"]["autonomy_class"] == "human_review"
    assert d["actions_taken"] == ["analysis_comment_posted"]
    assert d["m3_proof"]["human_control_state"]["state"] == "human_review_required"
    # No terminal action has been published yet — the workflow is paused.

