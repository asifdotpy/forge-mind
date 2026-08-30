"""Contract tests: Phase 3 Tier 2 Domain Managers (SPEC-001 T300).

Exit criterion under test (plan.md Phase 3): concurrent manager execution
where coverage permits, with no cross-domain reconciliation.  Each manager
aggregates schema-valid EvidenceShards into a schema-valid DomainFinding
strictly within its own bounded domain (data-model.md Invariant 2), makes no
decision, emits no EvidenceShard, and preserves provenance references
(Invariant 7).

Canonical fixtures: FIXTURE-001 (code domain) and FIXTURE-002 (all three
domains).  FIXTURE-003 also exercises the managers through the fixture runner.
"""

import json

import jsonschema
import pytest

from forgemind import CONTRACTS_DIR, FIXTURES_INPUT_DIR
from forgemind.supervisor import Supervisor
from forgemind.domain_managers import (
    CodeIntelligenceManager,
    DeliveryHealthManager,
    DomainManagerError,
    ManagerCoordinator,
    ManagerRegistry,
    ProductionHealthManager,
)

SUPERVISOR = Supervisor()
DOMAIN_FINDING_SCHEMA = json.loads(
    (CONTRACTS_DIR / "domain-finding.schema.json").read_text(encoding="utf-8")
)


def _fixture_event(fixture_filename):
    data = json.loads(
        (FIXTURES_INPUT_DIR / fixture_filename).read_text(encoding="utf-8")
    )
    return data["event"]


def _dispatch_for(fixture_filename):
    return SUPERVISOR.process_event(_fixture_event(fixture_filename))


def _shard(domain, *, suffix, trace_id, situation_id, claims=None,
           worker="test-worker", confidence=0.8, risk="medium"):
    """Build a schema-valid EvidenceShard for ``domain``."""
    return {
        "evidence_shard_id": f"ES-{suffix}-{domain}",
        "situation_id": situation_id,
        "worker": worker,
        "domain": domain,
        "observations": [f"{domain} observation"],
        "claims": claims or [f"{domain} claim"],
        "evidence_ids": [f"E-{suffix}-{domain}"],
        "confidence": confidence,
        "risk_level": risk,
        "uncertainties": [f"{domain} uncertainty"],
        "affected_entities": ["auth-service"],
        "provenance": {"source": "test-harness"},
        "execution_trace_id": trace_id,
    }
# ---------------------------------------------------------------------------
# Each manager aggregates its own domain's evidence into a DomainFinding.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "manager_cls,domain",
    [
        (CodeIntelligenceManager, "code"),
        (DeliveryHealthManager, "delivery"),
        (ProductionHealthManager, "production"),
    ],
)
def test_each_manager_aggregates_its_bounded_domain(manager_cls, domain):
    result = _dispatch_for("FIXTURE-002-escalation.json")
    shard = _shard(
        domain,
        suffix=result["event"]["event_id"][4:],
        trace_id=result["execution_trace_id"],
        situation_id=result["event"]["situation_id"],
        worker="fixture-worker",
    )
    finding = manager_cls().build_finding(
        result["supervisor_dispatch"], result["coverage_plan"], [shard]
    )
    assert finding["domain"] == domain
    assert finding["evidence_shard_ids"] == [f"ES-2000-{domain}"]
    assert finding["situation_id"] == result["event"]["situation_id"]
    # Conservative confidence aggregation: min across shards.
    assert finding["confidence"] == shard["confidence"]


def test_code_manager_aggregates_code_evidence():
    result = _dispatch_for("FIXTURE-001-happy-path.json")
    shard = _shard(
        "code",
        suffix="1000",
        trace_id=result["execution_trace_id"],
        situation_id=result["event"]["situation_id"],
    )
    finding = CodeIntelligenceManager().build_finding(
        result["supervisor_dispatch"], result["coverage_plan"], [shard]
    )
    assert finding["finding_id"] == "FND-1000-code"
    assert finding["supported_claims"] == ["code claim"]
    assert finding["uncertainties"] == ["code uncertainty"]
    assert finding["conflicts"] == []


# ---------------------------------------------------------------------------
# DomainFinding schema conformance + provenance (Invariant 7).
# ---------------------------------------------------------------------------


def test_domain_finding_validates_against_schema():
    result = _dispatch_for("FIXTURE-001-happy-path.json")
    shard = _shard(
        "code",
        suffix="1000",
        trace_id=result["execution_trace_id"],
        situation_id=result["event"]["situation_id"],
    )
    finding = CodeIntelligenceManager().build_finding(
        result["supervisor_dispatch"], result["coverage_plan"], [shard]
    )
    jsonschema.validate(finding, DOMAIN_FINDING_SCHEMA)


def test_domain_finding_provenance_references_upstream_ids():
    result = _dispatch_for("FIXTURE-001-happy-path.json")
    shard = _shard(
        "code",
        suffix="1000",
        trace_id=result["execution_trace_id"],
        situation_id=result["event"]["situation_id"],
    )
    finding = CodeIntelligenceManager().build_finding(
        result["supervisor_dispatch"], result["coverage_plan"], [shard]
    )
    prov = finding["provenance"]
    assert prov["event_id"] == result["event"]["event_id"] == "EVT-1000"
    assert prov["coverage_plan_id"] == result["coverage_plan"]["coverage_plan_id"]
    assert prov["execution_trace_id"] == result["execution_trace_id"]
    assert finding["execution_trace_id"] == result["execution_trace_id"]
    assert prov["evidence_shard_ids"] == finding["evidence_shard_ids"]
# ---------------------------------------------------------------------------
# Cross-domain evidence is rejected (Invariant 2).
# ---------------------------------------------------------------------------


def test_cross_domain_evidence_raises_domain_manager_error():
    result = _dispatch_for("FIXTURE-002-escalation.json")
    shard = _shard(
        "delivery",
        suffix="2000",
        trace_id=result["execution_trace_id"],
        situation_id=result["event"]["situation_id"],
    )
    with pytest.raises(DomainManagerError, match="bounded domain"):
        CodeIntelligenceManager().build_finding(
            result["supervisor_dispatch"], result["coverage_plan"], [shard]
        )


# ---------------------------------------------------------------------------
# Manager selection guard: never aggregate an unselected domain.
# ---------------------------------------------------------------------------


def test_manager_rejects_coverage_that_did_not_select_its_domain():
    result = _dispatch_for("FIXTURE-001-happy-path.json")  # code only
    shard = _shard(
        "delivery",
        suffix="1000",
        trace_id=result["execution_trace_id"],
        situation_id=result["event"]["situation_id"],
    )
    with pytest.raises(DomainManagerError, match="was not selected"):
        DeliveryHealthManager().build_finding(
            result["supervisor_dispatch"], result["coverage_plan"], [shard]
        )


def test_registry_returns_the_three_concrete_managers():
    registry = ManagerRegistry()
    assert isinstance(registry.get("code"), CodeIntelligenceManager)
    assert isinstance(registry.get("delivery"), DeliveryHealthManager)
    assert isinstance(registry.get("production"), ProductionHealthManager)


def test_registry_rejects_unknown_domain():
    with pytest.raises(DomainManagerError, match="unknown domain"):
        ManagerRegistry().get("unknown")
# ---------------------------------------------------------------------------
# Empty evidence → finding with empty arrays, not an error.
# ---------------------------------------------------------------------------


def test_empty_evidence_yields_finding_with_empty_arrays():
    result = _dispatch_for("FIXTURE-001-happy-path.json")
    finding = CodeIntelligenceManager().build_finding(
        result["supervisor_dispatch"], result["coverage_plan"], None
    )
    assert finding["evidence_shard_ids"] == []
    assert finding["supported_claims"] == []
    assert finding["conflicts"] == []
    assert finding["confidence"] == 0.0
    jsonschema.validate(finding, DOMAIN_FINDING_SCHEMA)


# ---------------------------------------------------------------------------
# Concurrent execution: the coordinator runs each selected manager per its
# own domain (FIXTURE-002 covers all three; FIXTURE-001 covers code only).
# ---------------------------------------------------------------------------


def test_coordinator_dispatch_for_multi_domain_fixture():
    result = _dispatch_for("FIXTURE-002-escalation.json")
    shards = [
        _shard(
            domain,
            suffix="2000",
            trace_id=result["execution_trace_id"],
            situation_id=result["event"]["situation_id"],
            worker="fixture-worker",
        )
        for domain in ("code", "delivery", "production")
    ]
    outcome = ManagerCoordinator().dispatch(
        result["supervisor_dispatch"], result["coverage_plan"], shards
    )
    assert outcome["rejected"] == []
    assert outcome["errors"] == {}
    assert set(outcome["findings"]) == {"code", "delivery", "production"}
    for domain, finding in outcome["findings"].items():
        assert finding["domain"] == domain
        jsonschema.validate(finding, DOMAIN_FINDING_SCHEMA)


def test_coordinator_rejects_evidence_for_unselected_domain():
    result = _dispatch_for("FIXTURE-001-happy-path.json")  # code + production (ADR-014)
    shards = [
        _shard(
            "code",
            suffix="1000",
            trace_id=result["execution_trace_id"],
            situation_id=result["event"]["situation_id"],
        ),
        _shard(
            "delivery",
            suffix="1000",
            trace_id=result["execution_trace_id"],
            situation_id=result["event"]["situation_id"],
        ),
    ]
    outcome = ManagerCoordinator().dispatch(
        result["supervisor_dispatch"], result["coverage_plan"], shards
    )
    assert set(outcome["findings"]) == {"code"}
    assert any("unselected domain" in note for note in outcome["rejected"])


# ---------------------------------------------------------------------------
# Fixture dispatch matrix: FIXTURE-001 -> code + production (ADR-014: auth
# files); FIXTURE-002 -> all three.
# ---------------------------------------------------------------------------


def test_fixture_001_dispatches_code_intelligence_manager():
    result = _dispatch_for("FIXTURE-001-happy-path.json")
    assert result["coverage_plan"]["selected_domains"] == ["code", "production"]
    assert result["supervisor_dispatch"]["selected_managers"] == [
        "code-intelligence-manager",
        "production-health-manager",
    ]


def test_fixture_002_dispatches_all_three_managers():
    result = _dispatch_for("FIXTURE-002-escalation.json")
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