"""Contract tests: Phase 6 Tier 5 Decision Reducer + ActionValidation (T600).

Exit criteria under test (plan.md Phase 6): no final action bypasses
validation; a safe action or an escalation is published.  The reducer
consumes ONLY ValidatedSituations (ADR-006), applies the deterministic
autonomy ladder (escalate < 0.5 <= review < 0.8 <= autonomous), and the
downstream Action Validation gate is the structural no-bypass point:
every terminal Action or Escalation flows through
``publish_terminal_output`` with a matching, fresh ActionValidation.
"""

import json

import jsonschema
import pytest

from forgemind import (
    CONTRACTS_DIR,
    FIXTURES_INPUT_DIR,
    ActionGateError,
    ActionValidationGate,
    CrossLifecycleValidator,
    DecisionReducer,
    ManagerCoordinator,
    ReducerError,
    Supervisor,
    acquire_event,
    publish_terminal_output,
)

DR_SCHEMA = json.loads(
    (CONTRACTS_DIR / "decision-record.schema.json").read_text(encoding="utf-8")
)
PA_SCHEMA = json.loads(
    (CONTRACTS_DIR / "proposed-action.schema.json").read_text(encoding="utf-8")
)
AV_SCHEMA = json.loads(
    (CONTRACTS_DIR / "action-validation.schema.json").read_text(encoding="utf-8")
)
ESC_SCHEMA = json.loads(
    (CONTRACTS_DIR / "escalation.schema.json").read_text(encoding="utf-8")
)

VALIDATOR = CrossLifecycleValidator()
REDUCER = DecisionReducer()
GATE = ActionValidationGate()


def _plan_and_dispatch(fixture_filename):
    """Acquire a fixture event and run the Tier 1 Supervisor over it."""
    data = json.loads(
        (FIXTURES_INPUT_DIR / fixture_filename).read_text(encoding="utf-8")
    )
    acquired = acquire_event(data["event"])
    plan = acquired["coverage_plan"]
    dispatch = Supervisor().dispatch(plan)
    return acquired["event"], dispatch, plan


def _finding(plan, domain, claims, *, confidence=0.8, uncertainties=None):
    """Build a schema-valid DomainFinding bound to ``plan``'s lineage."""
    situation_id = plan["situation_id"]
    suffix = (
        situation_id[len("SIT-"):]
        if situation_id.startswith("SIT-")
        else str(situation_id)
    )
    event_id = (plan.get("provenance") or {}).get("event_id", f"EVT-{suffix}")
    base = {
        "finding_id": f"FND-{suffix}-{domain}",
        "situation_id": situation_id,
        "domain": domain,
        "evidence_shard_ids": [f"ES-{suffix}-{domain}"],
        "summary": f"{domain} finding crafted for reducer contract tests",
        "supported_claims": list(claims),
        "conflicts": [],
        "coverage": {"domain": domain, "evidence_shard_count": 1},
        "confidence": confidence,
        "uncertainties": list(uncertainties or []),
        "provenance": {
            "event_id": event_id,
            "situation_id": situation_id,
            "coverage_plan_id": plan["coverage_plan_id"],
            "execution_trace_id": plan["execution_trace_id"],
            "produced_by": "ContractTestHarness",
        },
        "execution_trace_id": plan["execution_trace_id"],
    }
    jsonschema.validate(base, json.loads(
        (CONTRACTS_DIR / "domain-finding.schema.json").read_text(encoding="utf-8")
    ))
    return base


_VERIFIED_CLAIM = (
    "verified: the auth-service config rollback caused the elevated "
    "error rate"
)


def _strong_situation():
    """Full coverage + verified causal corroboration -> safe_autonomous."""
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    findings = [
        _finding(
            plan,
            "code",
            [
                _VERIFIED_CLAIM,
                "the deployed changeset touches the authentication request path",
            ],
            confidence=0.92,
        ),
        _finding(
            plan,
            "delivery",
            [_VERIFIED_CLAIM, "the build pipeline reported zero blocking failures"],
            confidence=0.9,
        ),
        _finding(
            plan,
            "production",
            ["the auth-service error rate recovered after the revert"],
            confidence=0.88,
        ),
    ]
    return VALIDATOR.validate(plan, findings), plan


def _correlated_situation(confidence=0.65):
    """Full coverage, correlation-only causality (no causal language)."""
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    shared = "the deploy window overlapped the error spike window"
    findings = [
        _finding(plan, "code", [shared], confidence=round(confidence + 0.05, 2)),
        _finding(plan, "delivery", [shared], confidence=confidence),
        _finding(
            plan,
            "production",
            ["the auth-service p99 latency doubled"],
            confidence=0.75,
        ),
    ]
    return VALIDATOR.validate(plan, findings), plan


def _low_confidence_situation(base_confidence=0.45):
    """Full coverage but weakest-link confidence below the escalate line."""
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    shared = "the deploy window overlapped the error spike window"
    findings = [
        _finding(plan, "code", [shared], confidence=0.55),
        _finding(plan, "delivery", [shared], confidence=base_confidence),
        _finding(
            plan,
            "production",
            ["the auth-service p99 latency doubled"],
            confidence=0.6,
        ),
    ]
    return VALIDATOR.validate(plan, findings), plan


def _coverage_gap_situation():
    """High confidence but one selected domain never contributed."""
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    findings = [
        _finding(plan, "code", [_VERIFIED_CLAIM], confidence=0.9),
        _finding(plan, "delivery", [_VERIFIED_CLAIM], confidence=0.85),
    ]
    return VALIDATOR.validate(plan, findings), plan


def _conflict_situation():
    """Cross-domain negation pair at high confidence."""
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    findings = [
        _finding(
            plan,
            "code",
            ["retry logic guards the refresh-token route"],
            confidence=0.9,
        ),
        _finding(
            plan,
            "delivery",
            ["the build pipeline reported zero blocking failures"],
            confidence=0.9,
        ),
        _finding(
            plan,
            "production",
            ["no retry logic guards the refresh-token route"],
            confidence=0.9,
        ),
    ]
    return VALIDATOR.validate(plan, findings), plan


def _record(**overrides):
    """Build a schema-valid DecisionRecord (for negative gate tests)."""
    base = {
        "decision_record_id": "DR-OTHER",
        "validated_situation_id": "VS-OTHER",
        "decision": "foreign record crafted for negative tests",
        "rationale": [],
        "risk_level": "low",
        "autonomy_class": "safe_autonomous",
        "confidence": 0.9,
        "uncertainties": [],
        "requires_human": False,
    }
    base.update(overrides)
    jsonschema.validate(base, DR_SCHEMA)
    return base


# -------------
# Tier 5 input discipline (ADR-006: consumes ONLY validated situations)
# -------------


def test_reduce_rejects_raw_domain_finding():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    with pytest.raises(ReducerError, match="only ValidatedSituation|not a schema-valid"):
        REDUCER.reduce(_finding(plan, "code", ["some claim"]))


def test_reduce_rejects_schema_invalid_situation():
    situation, _plan = _strong_situation()
    situation["validated_situation_id"] = "BOGUS-NOT-A-SITUATION"
    with pytest.raises(ReducerError, match="validated-situation.schema.json"):
        REDUCER.reduce(situation)


def test_reduce_accepts_only_validated_situation_type():
    with pytest.raises(ReducerError, match="only ValidatedSituation objects"):
        REDUCER.reduce(["not", "a", "dict"])


# -------------
# Deterministic autonomy ladder
# -------------


def test_safe_autonomous_produces_action_without_escalation():
    situation, plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    record = outcome["decision_record"]
    action = outcome["proposed_action"]

    assert outcome["escalation"] is None
    assert record["autonomy_class"] == "safe_autonomous"
    assert record["requires_human"] is False
    assert record["decision_record_id"] == "DR-2000"
    assert (
        record["validated_situation_id"]
        == situation["validated_situation_id"]
    )
    jsonschema.validate(record, DR_SCHEMA)
    assert action["action_id"] == "ACT-2000"
    assert action["decision_id"] == record["decision_record_id"]
    jsonschema.validate(action, PA_SCHEMA)


def test_safe_autonomous_risk_low_and_status_proposed():
    situation, _plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    record = outcome["decision_record"]
    action = outcome["proposed_action"]
    assert record["risk_level"] == "low"
    assert action["required_authority"] == "none"
    # Boundary: the reducer proposes; it never marks execution.
    assert action["status"] == "proposed"


def test_human_review_on_mid_band_confidence():
    situation, _plan = _correlated_situation(confidence=0.65)
    outcome = REDUCER.reduce(situation)
    record = outcome["decision_record"]
    action = outcome["proposed_action"]

    assert outcome["escalation"] is None
    assert record["autonomy_class"] == "human_review"
    assert record["requires_human"] is True
    assert record["risk_level"] == "medium"
    assert action["required_authority"] == "engineering-on-call"
    jsonschema.validate(record, DR_SCHEMA)
    jsonschema.validate(action, PA_SCHEMA)


def test_human_review_when_causality_not_established():
    # Confidence above the autonomous line but correlation-only evidence.
    situation, _plan = _correlated_situation(confidence=0.8)
    outcome = REDUCER.reduce(situation)
    record = outcome["decision_record"]
    assert record["autonomy_class"] == "human_review"
    assert record["requires_human"] is True


def test_escalates_below_half_confidence_with_uncertainty_reason():
    situation, plan = _low_confidence_situation(base_confidence=0.45)
    outcome = REDUCER.reduce(situation)

    assert outcome["proposed_action"] is None
    escalation = outcome["escalation"]
    jsonschema.validate(escalation, ESC_SCHEMA)
    assert outcome["decision_record"]["autonomy_class"] == "escalate"
    assert outcome["decision_record"]["requires_human"] is True
    assert escalation["reason"] == "uncertainty"
    assert escalation["situation_id"] == plan["situation_id"]


def test_escalates_on_coverage_gap_with_priority_reason():
    # High confidence + established causality, but a selected domain is
    # missing: coverage_gap wins over every other consideration.
    situation, _plan = _coverage_gap_situation()
    outcome = REDUCER.reduce(situation)
    assert outcome["proposed_action"] is None
    assert outcome["decision_record"]["confidence"] == 0.85  # above 0.5!
    assert outcome["escalation"]["reason"] == "coverage_gap"


def test_escalates_on_cross_domain_conflict():
    situation, _plan = _conflict_situation()
    outcome = REDUCER.reduce(situation)
    assert outcome["proposed_action"] is None
    record = outcome["decision_record"]
    escalation = outcome["escalation"]
    jsonschema.validate(escalation, ESC_SCHEMA)
    assert record["autonomy_class"] == "escalate"
    assert record["risk_level"] == "high"
    assert escalation["reason"] == "uncertainty"  # no coverage gap here


def test_escalation_preserves_evidence_ids_and_role():
    low, _plan = _low_confidence_situation(base_confidence=0.4)
    escalation = REDUCER.escalate(low)
    jsonschema.validate(escalation, ESC_SCHEMA)
    assert escalation["evidence_ids"]
    for evidence_id in low["evidence_ids"]:
        assert evidence_id in escalation["evidence_ids"]
    assert escalation["required_human_role"] == "engineering-on-call"
    assert escalation["escalation_id"] == "ESC-2000"


def test_escalate_rejects_unknown_reason():
    low, _plan = _low_confidence_situation()
    with pytest.raises(ReducerError, match="unknown escalation reason"):
        REDUCER.escalate(low, reason="because-i-said-so")


def test_exactly_one_terminal_branch_invariant():
    situations = [
        _strong_situation()[0],
        _correlated_situation()[0],
        _low_confidence_situation()[0],
        _coverage_gap_situation()[0],
        _conflict_situation()[0],
    ]
    for situation in situations:
        outcome = REDUCER.reduce(situation)
        assert (outcome["proposed_action"] is None) != (
            outcome["escalation"] is None
        ), "a reduction must produce exactly one terminal branch"


def test_reduction_is_replay_stable():
    situation, _plan = _strong_situation()
    first = REDUCER.reduce(situation)
    second = REDUCER.reduce(situation)
    assert first == second
    assert first["decision_record"] is not second["decision_record"]


def test_uncertainties_preserved_verbatim_into_record():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    shared = "the deploy window overlapped the error spike window"
    findings = [
        _finding(
            plan,
            "code",
            [shared],
            confidence=0.65,
            uncertainties=["caller graph partial"],
        ),
        _finding(
            plan,
            "delivery",
            [shared],
            confidence=0.7,
            uncertainties=["flaky suite baseline"],
        ),
        _finding(plan, "production", ["prod claim"], confidence=0.75),
    ]
    situation = VALIDATOR.validate(plan, findings)
    outcome = REDUCER.reduce(situation)
    assert "caller graph partial" in outcome["decision_record"]["uncertainties"]
    assert "flaky suite baseline" in outcome["decision_record"]["uncertainties"]


def test_decision_rationale_records_threshold_accounting():
    situation, _plan = _strong_situation()
    rationale = "\n".join(
        REDUCER.reduce(situation)["decision_record"]["rationale"]
    )
    assert "safe_autonomous" in rationale
    assert "0.8" in rationale and "0.5" in rationale
    assert "causality_status='verified'" in rationale


# -------------
# Downstream Action Validation & Safety Gate (no-bypass boundary)
# -------------


def test_gate_allows_with_deterministic_validated_at():
    situation, _plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    gated = GATE.validate(
        outcome["proposed_action"],
        outcome["decision_record"],
        event_timestamp="2026-08-21T10:00:00Z",
    )
    av = gated["action_validation"]
    jsonschema.validate(av, AV_SCHEMA)
    assert av["policy_result"] == "allowed"
    # Derived from the event timestamp — never the wall clock.
    assert av["validated_at"] == "2026-08-21T10:00:00Z"
    assert [c["check"] for c in av["checks"]] == [
        "schema-conformance",
        "decision-lineage",
        "blast-radius",
        "authorization-boundary",
    ]
    assert all(c["passed"] for c in av["checks"])
    # The action copy advances proposed -> validated.
    assert gated["proposed_action"]["status"] == "validated"


def test_gate_rejects_critical_blast_radius():
    situation, _plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    hot = dict(outcome["proposed_action"])
    hot["risk_level"] = "critical"
    gated = GATE.validate(
        hot,
        outcome["decision_record"],
        event_timestamp="2026-08-21T10:00:00Z",
    )
    assert gated["action_validation"]["policy_result"] == "rejected"
    assert gated["proposed_action"]["status"] == "rejected"

    published = publish_terminal_output(
        gated["proposed_action"],
        gated["action_validation"],
        situation_id="SIT-2000",
    )
    assert published["terminal"] == "escalation"
    jsonschema.validate(published["escalation"], ESC_SCHEMA)
    assert published["escalation"]["reason"] == "validation_failure"
    assert published["action"]["status"] == "escalated"


def test_gate_requires_human_for_external_authority():
    situation, _plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    gated_action = dict(outcome["proposed_action"])
    gated_action["required_authority"] = "deploy-bot-production"
    gated = GATE.validate(
        gated_action,
        outcome["decision_record"],
        event_timestamp="2026-08-21T10:00:00Z",
    )
    assert gated["action_validation"]["policy_result"] == "requires_human"
    # Awaiting human authority: still merely proposed.
    assert gated["proposed_action"]["status"] == "proposed"

    published = publish_terminal_output(
        gated["proposed_action"],
        gated["action_validation"],
        situation_id="SIT-2000",
        evidence_ids=["ES-2000-code"],
    )
    jsonschema.validate(published["escalation"], ESC_SCHEMA)
    assert published["escalation"]["reason"] == "policy_boundary"
    assert published["escalation"]["evidence_ids"] == ["ES-2000-code"]


def test_gate_rejects_broken_decision_lineage():
    situation, _plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    with pytest.raises(ActionGateError, match="broken decision lineage"):
        GATE.validate(
            outcome["proposed_action"],
            _record(),  # foreign DecisionRecord
            event_timestamp="2026-08-21T10:00:00Z",
        )


def test_publisher_executes_only_allowed_actions():
    situation, _plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    gated = GATE.validate(
        outcome["proposed_action"],
        outcome["decision_record"],
        event_timestamp="2026-08-21T10:00:00Z",
    )
    published = publish_terminal_output(
        gated["proposed_action"],
        gated["action_validation"],
        situation_id="SIT-2000",
    )
    assert published["terminal"] == "action"
    assert published["escalation"] is None
    jsonschema.validate(published["action"], PA_SCHEMA)
    assert published["action"]["status"] == "executed"


def test_publisher_blocks_forged_and_stale_validations():
    situation, _plan = _strong_situation()
    outcome = REDUCER.reduce(situation)
    action = outcome["proposed_action"]
    gated = GATE.validate(
        action, outcome["decision_record"], event_timestamp="2026-08-21T10:00:00Z"
    )

    # Bypass attempt 1: publish WITHOUT the gate (self-approved record).
    # The publisher refuses it — here via the stale-status guard, because
    # the raw proposed action never advanced through the gate.
    with pytest.raises(ActionGateError, match="stale or tampered|gate bypass"):
        publish_terminal_output(
            action,
            {
                "validation_id": "AV-FORGED",
                "action_id": action["action_id"],
                "policy_result": "allowed",
                "checks": [],
                "reason": "self-approved",
                "validated_at": "2026-08-21T10:00:00Z",
            },
            situation_id="SIT-2000",
        )

    # Bypass attempt 2: validation belonging to a DIFFERENT action.
    other = dict(action)
    other["action_id"] = "ACT-SOMEONE-ELSE"
    with pytest.raises(ActionGateError, match="gate bypass"):
        publish_terminal_output(
            other,
            gated["action_validation"],
            situation_id="SIT-2000",
        )

    # Bypass attempt 3: stale status disagreeing with the policy result.
    stale = dict(gated["proposed_action"])
    stale["status"] = "executed"  # claims execution without an allowed gate
    with pytest.raises(ActionGateError, match="stale or tampered"):
        publish_terminal_output(
            stale,
            dict(gated["action_validation"], policy_result="rejected"),
            situation_id="SIT-2000",
        )


def test_full_chain_validator_to_published_terminal():
    """End-to-end: Tier 2 -> 4 -> 5 -> gate -> publisher over real findings."""
    _event, dispatch, plan = _plan_and_dispatch(
        "FIXTURE-003-domain-evidence.json"
    )
    data = json.loads(
        (FIXTURES_INPUT_DIR / "FIXTURE-003-domain-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    outcome = ManagerCoordinator().dispatch(
        dispatch, plan, data["evidence_shards"]
    )
    assert outcome["errors"] == {}
    situation = VALIDATOR.validate(
        plan, [outcome["findings"][d] for d in sorted(outcome["findings"])]
    )
    reduction = REDUCER.reduce(situation)

    if reduction["proposed_action"] is not None:
        gated = GATE.validate(
            reduction["proposed_action"],
            reduction["decision_record"],
            event_timestamp=_event["timestamp"],
        )
        published = publish_terminal_output(
            gated["proposed_action"],
            gated["action_validation"],
            situation_id=plan["situation_id"],
            evidence_ids=situation["evidence_ids"],
        )
        assert published["terminal"] in ("action", "escalation")
        assert published["action"]["status"] in ("executed", "escalated")
    else:
        escalation = reduction["escalation"]
        jsonschema.validate(escalation, ESC_SCHEMA)
        assert escalation["situation_id"] == plan["situation_id"]

    # No decision artifact ever appears on the upstream Tier 4 artifact.
    for key in ("decision_record_id", "action_id", "validation_id"):
        assert key not in situation



