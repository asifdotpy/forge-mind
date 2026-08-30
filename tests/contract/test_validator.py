"""Contract tests: Phase 5 Tier 4 Cross-Lifecycle Validator (SPEC-001 T500).

Exit criterion under test (plan.md Phase 5): multi-domain ValidatedSituations
reconstructible from provenance.  The validator gathers every selected
domain's DomainFinding, flags coverage gaps explicitly (never silently),
separates supporting from conflicting evidence, deduplicates repeated
signals, keeps causation conservative (correlation != causation), and never
emits a DecisionRecord / ProposedAction artifact.
"""

import json

import jsonschema
import pytest

from forgemind import (
    CONTRACTS_DIR,
    CrossLifecycleValidator,
    FIXTURES_INPUT_DIR,
    ManagerCoordinator,
    Supervisor,
    ValidatorError,
    acquire_event,
)

VS_SCHEMA = json.loads(
    (CONTRACTS_DIR / "validated-situation.schema.json").read_text(encoding="utf-8")
)
FINDING_SCHEMA = json.loads(
    (CONTRACTS_DIR / "domain-finding.schema.json").read_text(encoding="utf-8")
)

DECISION_KEYS = (
    "decision_record_id",
    "proposed_action_id",
    "action_id",
    "action_validation_id",
    "escalation_id",
)

VALIDATOR = CrossLifecycleValidator()


def _plan_and_dispatch(fixture_filename):
    """Acquire a fixture event and run the Tier 1 Supervisor over it."""
    data = json.loads(
        (FIXTURES_INPUT_DIR / fixture_filename).read_text(encoding="utf-8")
    )
    acquired = acquire_event(data["event"])
    plan = acquired["coverage_plan"]
    dispatch = Supervisor().dispatch(plan)
    return acquired["event"], dispatch, plan


def _pipeline_findings():
    """Run the real Tier 1 -> Tier 2 pipeline over FIXTURE-003 evidence."""
    _event, dispatch, plan = _plan_and_dispatch("FIXTURE-003-domain-evidence.json")
    data = json.loads(
        (FIXTURES_INPUT_DIR / "FIXTURE-003-domain-evidence.json").read_text(
            encoding="utf-8"
        )
    )
    outcome = ManagerCoordinator().dispatch(dispatch, plan, data["evidence_shards"])
    assert outcome["errors"] == {}
    return plan, [outcome["findings"][d] for d in sorted(outcome["findings"])]


def _finding(plan, domain, claims, *, confidence=0.8, uncertainties=None, shard_ids=None):
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
        "evidence_shard_ids": shard_ids or [f"ES-{suffix}-{domain}"],
        "summary": f"{domain} finding crafted for validator contract tests",
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
    jsonschema.validate(base, FINDING_SCHEMA)
    return base


# ---------------------------------------------------------------------------
# Emission: schema validity, deterministic id, enum membership.
# ---------------------------------------------------------------------------


def test_validated_situation_is_schema_valid():
    plan, findings = _pipeline_findings()
    validated = VALIDATOR.validate(plan, findings)
    jsonschema.validate(validated, VS_SCHEMA)
    assert validated["situation_id"] == plan["situation_id"]
    assert validated["validated_situation_id"] == (
        f"VS-{plan['situation_id'][len('SIT-'):]}-{len(findings)}"
    )
    assert validated["finding_ids"] == [f["finding_id"] for f in findings]


def test_causality_status_enum():
    allowed = {"unsupported", "correlated", "supported", "verified"}
    plan, findings = _pipeline_findings()
    # FIXTURE-003 claims share no text and carry no causal language, but
    # 3 domains contribute findings, so multi-domain correlation applies.
    pipeline_status = VALIDATOR.validate(plan, findings)["causality_status"]
    assert pipeline_status in allowed
    assert pipeline_status == "correlated"


def test_missing_domains_flagged_in_coverage():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    findings = [
        _finding(plan, "code", ["the changeset alters the authentication request path"])
    ]
    validated = VALIDATOR.validate(plan, findings)
    jsonschema.validate(validated, VS_SCHEMA)
    assert validated["coverage"]["provided_domains"] == ["code"]
    assert validated["coverage"]["missing_domains"] == ["delivery", "production"]
    assert validated["coverage"]["coverage_percentage"] == 33
    assert any("coverage gap" in note for note in validated["validation_notes"])


def test_supporting_and_conflicting_evidence_separated():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    shared = "both domains observed the staging rollout window"
    findings = [
        _finding(plan, "code", ["retry logic guards the refresh-token route"]),
        _finding(plan, "delivery", [shared]),
        _finding(
            plan,
            "production",
            [shared, "no retry logic guards the refresh-token route"],
        ),
    ]
    validated = VALIDATOR.validate(plan, findings)
    assert shared in validated["supporting_evidence"]
    assert len(validated["conflicting_evidence"]) == 1
    conflict = validated["conflicting_evidence"][0]
    assert "retry logic guards the refresh-token route" in conflict
    assert "code" in conflict and "production" in conflict
    assert validated["correlations"], "shared claim yields a correlation entry"
    assert validated["causality_status"] == "correlated"


def test_deduplication_collapses_repeated_signals():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    repeated = "shared telemetry burst observed"
    findings = [
        _finding(plan, "code", [repeated], shard_ids=["ES-X-code"]),
        _finding(
            plan,
            "production",
            [repeated],
            shard_ids=["ES-X-code", "ES-X-production"],
        ),
    ]
    validated = VALIDATOR.validate(plan, findings)
    joined = "\n".join(validated["deduplication"])
    assert f"duplicate signal '{repeated}'" in joined
    assert "ES-X-code collapsed" in joined


def test_provenance_references_event_and_situation():
    plan, findings = _pipeline_findings()
    validated = VALIDATOR.validate(plan, findings)
    provenance = validated["provenance"]
    assert provenance["event_id"] == plan["provenance"]["event_id"]
    assert provenance["situation_id"] == plan["situation_id"]
    assert provenance["coverage_plan_id"] == plan["coverage_plan_id"]
    assert provenance["execution_trace_id"] == plan["execution_trace_id"]
    assert provenance["produced_by"] == "CrossLifecycleValidator"
    assert provenance["spec_phase"] == "SPEC-001-phase-5-tier-4-validator"
    assert validated["execution_trace_id"] == plan["execution_trace_id"]


def test_confidence_is_average_of_findings():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    findings = [
        _finding(plan, "code", ["code claim"], confidence=0.9),
        _finding(plan, "delivery", ["delivery claim"], confidence=0.68),
        _finding(plan, "production", ["production claim"], confidence=0.75),
    ]
    validated = VALIDATOR.validate(plan, findings)
    assert validated["confidence"] == 0.78


def test_empty_findings_emit_conservative_valid_situation():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    validated = VALIDATOR.validate(plan, [])
    jsonschema.validate(validated, VS_SCHEMA)
    assert validated["confidence"] == 0.0
    assert validated["causality_status"] == "unsupported"
    assert len(validated["coverage"]["missing_domains"]) == 3


def test_uncertainties_preserved_from_findings():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    findings = [
        _finding(plan, "code", ["code claim"], uncertainties=["caller graph partial"]),
        _finding(
            plan,
            "delivery",
            ["delivery claim"],
            confidence=0.4,
            uncertainties=["flaky suite baseline"],
        ),
    ]
    validated = VALIDATOR.validate(plan, findings)
    assert validated["uncertainties"][:2] == [
        "caller graph partial",
        "flaky suite baseline",
    ]
    assert validated["uncertainties"][-1].startswith("low-confidence finding(s)")
    notes = "\n".join(validated["validation_notes"])
    assert "weakest-link" in notes and "FND-" in notes


def test_validator_error_on_invalid_finding():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    bad = _finding(plan, "code", ["some claim"])
    bad["finding_id"] = "BOGUS-NOT-A-FINDING"
    with pytest.raises(ValidatorError, match="domain-finding.schema.json"):
        VALIDATOR.validate(plan, [bad])


def test_finding_from_unselected_domain_raises():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-001-happy-path.json")
    # ADR-014: FIXTURE-001 selects code + production; delivery is unselected.
    with pytest.raises(ValidatorError, match="did not select"):
        VALIDATOR.validate(plan, [_finding(plan, "delivery", ["rogue claim"])])


def test_validator_error_on_unsupported_causation():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    findings = [
        _finding(plan, "code", ["the config rollback caused the error spike"])
    ]
    with pytest.raises(ValidatorError, match="without cross-domain supporting"):
        VALIDATOR.validate(plan, findings)


def test_supported_and_verified_require_cross_domain_corroboration():
    _event, _dispatch, plan = _plan_and_dispatch("FIXTURE-002-escalation.json")
    causal = "the config rollback caused the error spike"
    supported = VALIDATOR.validate(
        plan,
        [_finding(plan, "code", [causal]), _finding(plan, "delivery", [causal])],
    )
    assert supported["causality_status"] == "supported"

    verified_claim = "verified: the config rollback caused the error spike"
    verified = VALIDATOR.validate(
        plan,
        [
            _finding(plan, "code", [verified_claim]),
            _finding(plan, "delivery", [verified_claim]),
        ],
    )
    assert verified["causality_status"] == "verified"


def test_validation_is_idempotent_across_replays():
    plan, findings = _pipeline_findings()
    first = VALIDATOR.validate(plan, findings)
    second = VALIDATOR.validate(plan, findings)
    assert first == second
    assert first is not second
    first["coverage"]["provided_domains"].append("probe-mutation")
    third = VALIDATOR.validate(plan, findings)
    assert third == second  # stateless: caller-side mutation never leaks in


def test_validator_emits_no_decision_artifacts():
    plan, findings = _pipeline_findings()
    validated = VALIDATOR.validate(plan, findings)
    for key in DECISION_KEYS:
        assert key not in validated, f"Tier 4 leaked decision artifact {key!r}"