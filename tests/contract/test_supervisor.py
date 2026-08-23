"""Contract tests: Phase 2 Tier 1 Supervisor (SPEC-001 T200).

Exit criterion under test: the trace shows ``Supervisor -> selected
Managers + coverage decision`` — i.e. the Supervisor wraps Phase 1
acquisition unchanged, emits a ``SupervisorDispatch`` trace record
selecting exactly the CoveragePlan managers with a documented dispatch
rationale, and enforces the CoveragePlan's ``global_constraints``
without performing specialist analysis (Tier 2+) or emitting canonical
artifacts.

Canonical inputs: fixtures/inputs/FIXTURE-001-happy-path.json and
fixtures/inputs/FIXTURE-002-escalation.json (unchanged; the Supervisor
is escalation-agnostic — escalation semantics remain Phase 6).
"""

import json

import pytest

from forgemind import FIXTURES_INPUT_DIR
from forgemind.supervisor import Supervisor, SupervisorError

SUPERVISOR = Supervisor()


def _fixture_event(fixture_filename):
    data = json.loads(
        (FIXTURES_INPUT_DIR / fixture_filename).read_text(encoding="utf-8")
    )
    return data["event"]


@pytest.fixture(scope="module")
def processed_001():
    return SUPERVISOR.process_event(_fixture_event("FIXTURE-001-happy-path.json"))


# ---------------------------------------------------------------------------
# Trace shows Event -> CoveragePlan -> selected Managers (exit criterion)
# ---------------------------------------------------------------------------


def test_fixture_001_supervisor_dispatches_code_manager(processed_001):
    dispatch = processed_001["supervisor_dispatch"]
    assert dispatch["artifact_type"] == "SupervisorDispatch"
    assert dispatch["dispatched"] is True
    assert dispatch["selected_managers"] == ["code-intelligence-manager"]


def test_fixture_002_supervisor_dispatches_all_three_managers():
    result = SUPERVISOR.process_event(
        _fixture_event("FIXTURE-002-escalation.json")
    )
    assert result["coverage_plan"]["selected_domains"] == [
        "code",
        "delivery",
        "production",
    ]
    assert result["supervisor_dispatch"]["selected_managers"] == [
        "code-intelligence-manager",
        "delivery-health-manager",
        "production-health-manager",
    ]


def test_trace_links_event_to_coverage_plan_to_managers(processed_001):
    event = processed_001["event"]
    plan = processed_001["coverage_plan"]
    dispatch = processed_001["supervisor_dispatch"]
    assert event["event_id"] == "EVT-1000"
    assert plan["provenance"]["event_id"] == event["event_id"]
    assert (
        dispatch["coverage_plan_id"] == plan["coverage_plan_id"] == "CP-1000"
    )
    assert (
        dispatch["execution_trace_id"]
        == plan["execution_trace_id"]
        == processed_001["execution_trace_id"]
        == "TRC-1000"
    )
    assert dispatch["situation_id"] == event["situation_id"] == "SIT-1000"


def test_explicit_trace_id_propagates_to_dispatch():
    result = SUPERVISOR.process_event(
        _fixture_event("FIXTURE-001-happy-path.json"),
        execution_trace_id="TRC-custom-42",
    )
    dispatch = result["supervisor_dispatch"]
    assert dispatch["execution_trace_id"] == "TRC-custom-42"
    assert result["coverage_plan"]["execution_trace_id"] == "TRC-custom-42"


# ---------------------------------------------------------------------------
# Global constraints enriched + enforced
# ---------------------------------------------------------------------------


def test_coverage_plan_carries_phase2_global_constraints(processed_001):
    constraints = processed_001["coverage_plan"]["global_constraints"]
    assert constraints == {
        "max_concurrent_managers": 3,
        "global_timeout_seconds": 300,
        "require_human_above_risk_level": "critical",
    }


def test_coverage_plan_carries_phase2_coverage_requirements(processed_001):
    assert processed_001["coverage_plan"]["coverage_requirements"] == {
        "min_domains": 1,
        "max_domains": 3,
    }


def test_dispatch_carries_enforced_global_constraints(processed_001):
    plan = processed_001["coverage_plan"]
    dispatch = processed_001["supervisor_dispatch"]
    assert dispatch["global_constraints"] == plan["global_constraints"]


def test_max_concurrent_managers_violation_raises_supervisor_error():
    plan = SUPERVISOR.process_event(
        _fixture_event("FIXTURE-002-escalation.json")
    )["coverage_plan"]
    assert len(plan["selected_managers"]) == 3
    tightened = {
        **plan,
        "global_constraints": {
            **plan["global_constraints"],
            "max_concurrent_managers": 2,
        },
    }
    with pytest.raises(SupervisorError, match="max_concurrent_managers"):
        SUPERVISOR.dispatch(tightened)


def test_invalid_global_timeout_is_rejected(processed_001):
    plan = processed_001["coverage_plan"]
    broken = {
        **plan,
        "global_constraints": {
            **plan["global_constraints"],
            "global_timeout_seconds": 0,
        },
    }
    with pytest.raises(SupervisorError, match="global_timeout_seconds"):
        SUPERVISOR.dispatch(broken)


def test_invalid_require_human_above_risk_level_is_rejected(processed_001):
    plan = processed_001["coverage_plan"]
    broken = {
        **plan,
        "global_constraints": {
            **plan["global_constraints"],
            "require_human_above_risk_level": "apocalyptic",
        },
    }
    with pytest.raises(
        SupervisorError, match="require_human_above_risk_level"
    ):
        SUPERVISOR.dispatch(broken)


def test_min_domains_coverage_requirement_violation_raises(processed_001):
    plan = processed_001["coverage_plan"]
    broken = {
        **plan,
        "coverage_requirements": {"min_domains": 2, "max_domains": 3},
    }
    with pytest.raises(SupervisorError, match="min_domains"):
        SUPERVISOR.dispatch(broken)


# ---------------------------------------------------------------------------
# Dispatch decision & provenance
# ---------------------------------------------------------------------------


def test_dispatch_rationale_documents_the_decision(processed_001):
    rationale = processed_001["supervisor_dispatch"]["dispatch_rationale"]
    assert isinstance(rationale, list) and rationale
    joined = " ".join(rationale)
    assert "code-intelligence-manager" in joined
    assert "CP-1000" in joined
    assert "max_concurrent_managers=3" in joined
    assert "global_timeout_seconds=300" in joined
    assert "require_human_above_risk_level='critical'" in joined


def test_provenance_references_event_and_coverage_plan(processed_001):
    prov = processed_001["supervisor_dispatch"]["provenance"]
    assert prov["event_id"] == "EVT-1000"
    assert prov["coverage_plan_id"] == "CP-1000"


def test_selected_managers_must_match_coverage_plan(processed_001):
    plan = processed_001["coverage_plan"]
    tampered = {
        **plan,
        "selected_managers": [
            "code-intelligence-manager",
            "rogue-manager",
        ],
    }
    with pytest.raises(SupervisorError, match="do not match"):
        SUPERVISOR.dispatch(tampered)


def test_empty_plan_is_rejected():
    with pytest.raises(SupervisorError, match="missing required keys"):
        SUPERVISOR.dispatch({})


# ---------------------------------------------------------------------------
# Idempotency / determinism
# ---------------------------------------------------------------------------


def test_dispatch_is_idempotent_across_replays():
    event = _fixture_event("FIXTURE-001-happy-path.json")
    first = SUPERVISOR.process_event(event)
    second = SUPERVISOR.process_event(dict(event))
    assert first == second


# ---------------------------------------------------------------------------
# Tier boundary guards (Supervisor stays a global coordinator)
# ---------------------------------------------------------------------------


def test_supervisor_emits_no_canonical_artifacts_or_evidence(processed_001):
    dispatch = processed_001["supervisor_dispatch"]
    assert "evidence_shards" not in dispatch
    assert "domain_findings" not in dispatch
    # The Supervisor never narrows or rewrites the plan's artifact expectations.
    assert processed_001["coverage_plan"]["expected_artifacts"] == [
        "EvidenceShard",
        "DomainFinding",
        "ValidatedSituation",
        "DecisionRecord",
        "ProposedAction",
        "ActionValidation",
    ]


def test_supervisor_preserves_phase1_acquisition_result(processed_001):
    from forgemind.acquisition import acquire_event

    event = _fixture_event("FIXTURE-001-happy-path.json")
    acquired = acquire_event(event)
    assert processed_001["event"] == acquired["event"]
    assert processed_001["coverage_plan"] == acquired["coverage_plan"]