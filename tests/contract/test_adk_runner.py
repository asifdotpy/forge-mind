"""Contract tests for ADK 2.0 Runner tool-based pipeline (ADR-008, ADR-010).

Verifies:
1. Tool functions read from and write to tool_context.state
2. Pause/resume integration via _PENDING_APPROVALS store
3. Tool-wired root agent composition
4. Runner instantiation
5. Runtime selection flags (is_adk_runner_runtime, is_adk_runtime)
6. ADR-009 boundary for tools/adk_tools.py
7. Full pipeline envelope compatibility
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

from forgemind.acquisition import acquire_event
from forgemind.adk_app import create_adk_tool_runner, is_adk_available
from forgemind.adk_runtime import (
    _PENDING_APPROVALS,
    is_adk_runner_runtime,
    is_adk_runtime,
    resume_adk_pipeline,
)
from forgemind.agents.root_agent import build_runner_root_agent
from forgemind.tools.adk_tools import (
    call_action_gate,
    call_managers,
    call_reducer,
    call_supervisor,
    call_validator,
    call_workers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_INPUT_DIR = REPO_ROOT / "fixtures" / "inputs"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_INPUT_DIR / name).read_text(encoding="utf-8"))


class MockToolContext:
    """Mock ADK ToolContext providing state dict access."""

    def __init__(self, state: Dict[str, Any]):
        self.state = state


def test_adk_tools_chain_execution():
    """All 6 ADK tools execute in order, reading/writing tool_context.state."""
    fixture = _load_fixture("FIXTURE-007-m3-judge-surface-action.json")
    acquired = acquire_event(fixture["event"])
    plan = acquired["coverage_plan"]
    event = acquired["event"]

    state: Dict[str, Any] = {
        "event": event,
        "coverage_plan": plan,
        "repo": "test/repo",
        "sha": "123456",
        "event_timestamp": event["timestamp"],
        "evidence_shards": fixture.get("evidence_shards"),
        "domain_findings": fixture.get("domain_findings"),
        "workers": fixture.get("workers"),
    }
    ctx = MockToolContext(state)

    # 1. Supervisor
    sup_out = call_supervisor(ctx)
    assert "supervisor_dispatch" in ctx.state
    assert ctx.state["supervisor_dispatch"] == sup_out
    assert ctx.state["supervisor_dispatch"]["situation_id"] == "SIT-7000"

    # 2. Workers
    work_out = call_workers(ctx)
    assert "evidence_shards" in ctx.state
    assert len(ctx.state["evidence_shards"]) > 0

    # 3. Managers
    mgr_out = call_managers(ctx)
    assert "domain_findings" in ctx.state
    assert len(ctx.state["domain_findings"]) > 0

    # 4. Validator
    val_out = call_validator(ctx)
    assert "validated_situation" in ctx.state
    assert ctx.state["validated_situation"]["situation_id"] == "SIT-7000"

    # 5. Reducer
    red_out = call_reducer(ctx)
    assert "decision_record" in ctx.state
    assert "proposed_action" in ctx.state
    assert ctx.state["decision_record"]["risk_level"] == "low"
    assert ctx.state["proposed_action"] is not None

    # 6. Action Gate
    gate_out = call_action_gate(ctx)
    assert "terminal" in ctx.state
    assert ctx.state["terminal"]["type"] == "action"
    assert ctx.state["terminal"]["action_validation"]["policy_result"] == "allowed"


def test_adk_tool_action_gate_pause_and_resume():
    """call_action_gate writes to _PENDING_APPROVALS when policy_result is requires_human."""
    fixture = _load_fixture("FIXTURE-007-m3-judge-surface-action.json")
    findings = copy.deepcopy(fixture["domain_findings"])
    for f in findings:
        f["confidence"] = 0.6
        f["supported_claims"] = ["the auth-service error rate is elevated in staging"]
        f["summary"] = "mutated for requires_human"

    acquired = acquire_event(fixture["event"])
    plan = acquired["coverage_plan"]
    event = acquired["event"]

    state: Dict[str, Any] = {
        "event": event,
        "coverage_plan": plan,
        "repo": "test/repo",
        "sha": "123456",
        "event_timestamp": event["timestamp"],
        "domain_findings": findings,
    }
    ctx = MockToolContext(state)

    call_supervisor(ctx)
    call_workers(ctx)
    call_managers(ctx)
    call_validator(ctx)
    call_reducer(ctx)

    # Gate should pause
    gate_out = call_action_gate(ctx)
    assert gate_out["status"] == "paused"
    assert ctx.state["terminal"] is None
    assert ctx.state["pending_approval"] is not None

    token = ctx.state["pending_approval"]["token"]
    assert token in _PENDING_APPROVALS

    # Resuming via the standard approval function must work seamlessly
    resumed = resume_adk_pipeline(token, "approve")
    assert resumed["status"] == "ok"
    assert resumed["human_decision"] == "approve"
    assert resumed["terminal"]["type"] == "escalation"


@pytest.mark.skipif(not is_adk_available(), reason="google-adk not installed")
def test_build_runner_root_agent():
    """build_runner_root_agent composes 6 tool-wired sub-agents."""
    root = build_runner_root_agent()
    assert root.name == "forgemind_runner_root"
    assert len(root.sub_agents) == 6

    names = [a.name for a in root.sub_agents]
    assert names == [
        "supervisor",
        "workers",
        "managers",
        "validator",
        "reducer",
        "action_gate",
    ]

    # Every agent must have exactly 1 tool
    for agent in root.sub_agents:
        assert len(agent.tools) == 1
        assert agent.output_key is not None


@pytest.mark.skipif(not is_adk_available(), reason="google-adk not installed")
def test_create_adk_tool_runner():
    """create_adk_tool_runner constructs an instantiated ADK Runner."""
    runner = create_adk_tool_runner(app_name="forgemind_test")
    assert runner is not None
    assert runner.app_name == "forgemind_test"
    assert runner.agent.name == "forgemind_runner_root"


def test_runtime_flags(monkeypatch):
    """FORGEMIND_RUNTIME flag correctly activates adk+runner and adk modes."""
    monkeypatch.setenv("FORGEMIND_RUNTIME", "adk+runner")
    assert is_adk_runner_runtime() is True
    assert is_adk_runtime() is True

    monkeypatch.setenv("FORGEMIND_RUNTIME", "adk")
    assert is_adk_runner_runtime() is False
    assert is_adk_runtime() is True

    monkeypatch.setenv("FORGEMIND_RUNTIME", "deterministic")
    assert is_adk_runner_runtime() is False
    assert is_adk_runtime() is False

    monkeypatch.delenv("FORGEMIND_RUNTIME", raising=False)
    assert is_adk_runner_runtime() is False
    assert is_adk_runtime() is False


def test_no_chroma_in_adk_tools():
    """tools/adk_tools.py never imports chromadb (ADR-009 boundary)."""
    tools_path = REPO_ROOT / "src" / "forgemind" / "tools" / "adk_tools.py"
    content = tools_path.read_text(encoding="utf-8").lower()
    assert "chroma" not in content

    child_code = (
        "import importlib, sys\n"
        "class B:\n"
        "    def find_spec(self, name, path=None, target=None):\n"
        "        if name == 'chromadb' or name.startswith('chromadb.'):\n"
        "            raise ImportError('BLOCKED ' + name)\n"
        "        return None\n"
        "sys.meta_path.insert(0, B())\n"
        "importlib.import_module('forgemind.tools.adk_tools')\n"
        "print('ADK_TOOLS_IMPORT_OK')\n"
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
        f"adk_tools failed to import with chromadb blocked: {result.stdout} {result.stderr}"
    )
    assert "ADK_TOOLS_IMPORT_OK" in result.stdout


def test_adk_events_route_with_runner_runtime(monkeypatch):
    """POST /api/v1/adk/events under FORGEMIND_RUNTIME=adk+runner produces full envelope."""
    from fastapi.testclient import TestClient

    from forgemind.api import create_api

    monkeypatch.setenv("FORGEMIND_RUNTIME", "adk+runner")
    client = TestClient(create_api())

    fixture = _load_fixture("FIXTURE-007-m3-judge-surface-action.json")
    resp = client.post(
        "/api/v1/adk/events",
        json={
            "event": fixture["event"],
            "domain_findings": fixture.get("domain_findings"),
            "workers": fixture.get("workers"),
            "evidence_shards": fixture.get("evidence_shards"),
        },
    )
    assert resp.status_code == 200
    d = resp.json()
    assert d["status"] == "ok"
    assert d["autonomy"]["autonomy_class"] == "safe_autonomous"
    assert d["terminal"]["type"] == "action"
    assert "coverage_plan" in d["artifacts"]
    assert "validated_situation" in d["artifacts"]
