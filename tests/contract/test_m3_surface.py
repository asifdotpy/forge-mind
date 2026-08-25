"""M3-A contract tests for the judge-visible surface (T722).

Mirrors the fixture-driven pattern of ``tests/integration/test_fixture_run.py``:
loads canonical ``fixtures/inputs/*.json`` envelopes and drives
``forgemind.api.run_pipeline``, then asserts the presentation-only M3 proof
block derived by ``forgemind.m3_proof.build_m3_proof``.

Fixture choice (deviation from the M3-A plan text, empirically verified):
the plan names FIXTURE-001 as the *action* path, but FIXTURE-001 carries no
DomainFindings, so the pipeline honestly escalates (zero confidence, coverage
gap).  The action path is therefore exercised with
``FIXTURE-007-m3-judge-surface-action.json`` (T711), which supplies verified
multi-domain findings and reaches ``terminal.type == "action"`` /
``policy_result == "allowed"``.  The escalation path uses both FIXTURE-002 and
``FIXTURE-007-m3-judge-surface-escalation.json``.
"""

import json
from pathlib import Path

import pytest

from forgemind.api import EventInput, _render_situation_html, run_pipeline
from forgemind.m3_proof import build_m3_proof

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_INPUT = REPO_ROOT / "fixtures" / "inputs"

ACTION_FIXTURE = "FIXTURE-007-m3-judge-surface-action.json"
ESCALATION_FIXTURES = (
    "FIXTURE-002-escalation.json",
    "FIXTURE-007-m3-judge-surface-escalation.json",
)

EXPECTED_CHAIN = [
    "coverage_plan",
    "evidence_shards",
    "domain_findings",
    "validated_situation",
    "decision_record",
    "action_validation",
    "terminal",
]


def _run(name: str) -> dict:
    payload = json.loads((FIXTURES_INPUT / name).read_text(encoding="utf-8"))
    return run_pipeline(EventInput(**payload))


@pytest.fixture(scope="module")
def action_result() -> dict:
    return _run(ACTION_FIXTURE)


@pytest.fixture(scope="module")
def escalation_result() -> dict:
    return _run(ESCALATION_FIXTURES[0])


def test_m3_proof_present_on_events_response(action_result, escalation_result):
    """The pipeline response carries the four judge-visible blocks."""
    for result in (action_result, escalation_result):
        assert "m3_proof" in result
        assert set(result["m3_proof"]) == {
            "provenance_links",
            "validation_verdict",
            "uncertainty_summary",
            "human_control_state",
        }
        # Pure helper reproduces the attached block exactly.
        assert build_m3_proof(result) == result["m3_proof"]

    # Defensive derivation: missing keys yield None/empty, never a crash.
    empty = build_m3_proof({})
    assert empty["provenance_links"]["event_id"] is None
    assert len(empty["provenance_links"]["artifact_chain"]) == 7
    assert empty["validation_verdict"]["state"] == "escalated"
    assert empty["uncertainty_summary"]["uncertainties"] == []
    assert empty["human_control_state"]["autonomy_class"] is None


def test_provenance_links_have_trace_ids(action_result):
    links = action_result["m3_proof"]["provenance_links"]
    assert links["event_id"] == "EVT-7000"
    assert links["situation_id"] == action_result["situation_id"]
    assert links["execution_trace_id"] == action_result["trace_id"]
    assert links["coverage_plan_id"]
    chain = links["artifact_chain"]
    assert len(chain) == 7
    assert [entry["artifact"] for entry in chain] == EXPECTED_CHAIN
    assert all(entry["upstream"] for entry in chain)


def test_validation_verdict_action(action_result):
    verdict = action_result["m3_proof"]["validation_verdict"]
    assert action_result["terminal"]["type"] == "action"
    assert verdict["state"] == "automated"
    assert verdict["policy_result"] == "allowed"
    assert verdict["validation_id"]


def test_validation_verdict_escalation():
    for fixture_name in ESCALATION_FIXTURES:
        result = _run(fixture_name)
        proof = result["m3_proof"]
        assert result["terminal"]["type"] == "escalation", fixture_name
        assert proof["validation_verdict"]["state"] == "escalated", fixture_name
        assert proof["human_control_state"]["required_human_role"], fixture_name


def test_uncertainty_summary_shape(action_result, escalation_result):
    for result in (action_result, escalation_result):
        summary = result["m3_proof"]["uncertainty_summary"]
        assert summary["causality_status"] in {
            "unsupported",
            "correlated",
            "supported",
            "verified",
        }
        assert isinstance(summary["confidence"], (int, float))
        assert 0.0 <= float(summary["confidence"]) <= 1.0
        assert isinstance(summary["missing_domains"], list)
        assert isinstance(summary["uncertainties"], list)


def test_human_control_state_derivation(action_result, escalation_result):
    action_control = action_result["m3_proof"]["human_control_state"]
    assert action_control["state"] == "automated"
    assert action_control["autonomy_class"] == "safe_autonomous"
    assert action_control["required_human_role"] is None
    assert action_control["risk_level"]

    esc_control = escalation_result["m3_proof"]["human_control_state"]
    assert esc_control["state"] == "escalated"
    assert esc_control["autonomy_class"] == "escalate"
    assert esc_control["required_human_role"] is not None

    # T721: the offline viewer renders the same four properties (no CDN assets).
    html = _render_situation_html(escalation_result)
    for token in ("provenance", "validation", "uncertainty", "human control"):
        assert token in html
    assert escalation_result["situation_id"] in html
    assert "http://" not in html and "https://" not in html
