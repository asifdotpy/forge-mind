"""Contract tests: Phase 4 Tier 3 Specialist Workers (SPEC-001 T400).

Exit criterion under test (plan.md Phase 4): durable EvidenceShards with
provenance and NO decisions.  Each worker emits a schema-valid EvidenceShard
within its bounded domain (Invariant 1), preserves uncertainty and provenance
(Invariant 7), and never emits a DecisionRecord / ValidatedSituation /
DomainFinding / ProposedAction artifact.  The coordinator runs selected
workers independently (concurrently by default).
"""

import json

import jsonschema
import pytest

from forgemind import CONTRACTS_DIR, FIXTURES_INPUT_DIR
from forgemind.supervisor import Supervisor
from forgemind.workers import (
    AlertStormClusteringWorker,
    BuildLogAndFlakinessWorker,
    DocsDriftAndSpecWorker,
    PRPreFlightASTWorker,
    SecurityAndDependencyWorker,
    TelemetryCorrelationWorker,
    Worker,
    WorkerCoordinator,
    WorkerError,
    WorkerRegistry,
)

SUPERVISOR = Supervisor()
SHARD_SCHEMA = json.loads(
    (CONTRACTS_DIR / "evidence-shard.schema.json").read_text(encoding="utf-8")
)

ALL_WORKER_CLASSES = (
    PRPreFlightASTWorker,
    DocsDriftAndSpecWorker,
    BuildLogAndFlakinessWorker,
    AlertStormClusteringWorker,
    TelemetryCorrelationWorker,
    SecurityAndDependencyWorker,
)

FORBIDDEN_ARTIFACT_KEYS = (
    "finding_id",
    "validated_situation_id",
    "decision_record_id",
    "proposed_action_id",
    "action_id",
    "validation_id",
)


def _fixture_event(fixture_filename):
    data = json.loads(
        (FIXTURES_INPUT_DIR / fixture_filename).read_text(encoding="utf-8")
    )
    return data["event"]


def _plan_for(fixture_filename):
    """Run the Tier 1 Supervisor over a fixture event; return the CoveragePlan."""
    return SUPERVISOR.process_event(_fixture_event(fixture_filename))


def _context(domain, **overrides):
    """Build a bounded worker context for ``domain``."""
    base = {
        "domain": domain,
        "inputs": {},
        "confidence": 0.75,
        "risk_level": "medium",
        "affected_entities": ["auth-service"],
        "uncertainties": [f"{domain} uncertainty"],
    }
    base.update(overrides)
    return base
# ---------------------------------------------------------------------------
# Each of the six workers emits a schema-valid EvidenceShard in its domain.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "worker_cls,domain,worker_name",
    [
        (PRPreFlightASTWorker, "code", "pr-pre-flight-ast-worker"),
        (DocsDriftAndSpecWorker, "code", "docs-drift-and-spec-worker"),
        (BuildLogAndFlakinessWorker, "delivery", "build-log-and-flakiness-worker"),
        (AlertStormClusteringWorker, "delivery", "alert-storm-clustering-worker"),
        (TelemetryCorrelationWorker, "production", "telemetry-correlation-worker"),
        (SecurityAndDependencyWorker, "production", "security-and-dependency-worker"),
    ],
)
def test_each_worker_emits_schema_valid_shard(worker_cls, domain, worker_name):
    plan = _plan_for("FIXTURE-002-escalation.json")["coverage_plan"]
    worker = worker_cls()
    shard = worker.build_shard(plan, _context(domain))
    assert shard["worker"] == worker_name
    assert shard["domain"] == domain
    assert shard["situation_id"] == plan["situation_id"]
    assert shard["evidence_shard_id"].startswith("ES-")
    # Non-MVP workers still produce meaningful (non-empty) evidence content.
    assert shard["observations"], f"{worker_name} produced no observations"
    assert shard["claims"], f"{worker_name} produced no claims"
    jsonschema.validate(shard, SHARD_SCHEMA)


def test_mvp_worker_ids_are_pure_functions_of_event_and_worker():
    plan = _plan_for("FIXTURE-001-happy-path.json")["coverage_plan"]
    shard = PRPreFlightASTWorker().build_shard(
        plan, _context("code", inputs={"changed_files": ["auth/config.go"]})
    )
    assert shard["evidence_shard_id"] == "ES-1000-pr-pre-flight-ast-worker"


# ---------------------------------------------------------------------------
# Domain mismatch (Invariant 1) and unselected-domain guards.
# ---------------------------------------------------------------------------


def test_cross_domain_context_raises_worker_error():
    plan = _plan_for("FIXTURE-002-escalation.json")["coverage_plan"]
    with pytest.raises(WorkerError, match="bounded"):
        PRPreFlightASTWorker().build_shard(plan, _context("delivery"))


def test_cross_domain_finding_context_raises_worker_error():
    plan = _plan_for("FIXTURE-002-escalation.json")["coverage_plan"]
    context = _context("code", domain_finding={"domain": "delivery"})
    with pytest.raises(WorkerError, match="DomainFinding"):
        PRPreFlightASTWorker().build_shard(plan, context)


def test_worker_rejects_coverage_that_did_not_select_its_domain():
    plan = _plan_for("FIXTURE-001-happy-path.json")["coverage_plan"]  # code only
    with pytest.raises(WorkerError, match="was not selected"):
        BuildLogAndFlakinessWorker().build_shard(
            plan, _context("delivery", inputs={"ci_outcome": "pass"})
        )


# ---------------------------------------------------------------------------
# Provenance (Invariant 7) and boundary guards.
# ---------------------------------------------------------------------------


def test_shard_provenance_references_upstream_ids():
    result = _plan_for("FIXTURE-002-escalation.json")
    plan = result["coverage_plan"]
    shard = TelemetryCorrelationWorker().build_shard(
        plan, _context("production", inputs={"telemetry_signals": [12.5]})
    )
    prov = shard["provenance"]
    assert prov["event_id"] == result["event"]["event_id"]
    assert prov["coverage_plan_id"] == plan["coverage_plan_id"]
    assert prov["execution_trace_id"] == plan["execution_trace_id"]
    assert shard["execution_trace_id"] == plan["execution_trace_id"]
    assert prov["situation_id"] == plan["situation_id"]


def test_workers_emit_no_decision_or_finding_artifacts():
    plan = _plan_for("FIXTURE-002-escalation.json")["coverage_plan"]
    for worker_cls, domain in (
        (PRPreFlightASTWorker, "code"),
        (BuildLogAndFlakinessWorker, "delivery"),
        (TelemetryCorrelationWorker, "production"),
    ):
        shard = worker_cls().build_shard(plan, _context(domain))
        for forbidden in FORBIDDEN_ARTIFACT_KEYS:
            assert forbidden not in shard, (
                f"{worker_cls.__name__} leaked decision artifact {forbidden!r}"
            )


def test_uncertainty_is_preserved_in_the_shard():
    plan = _plan_for("FIXTURE-002-escalation.json")["coverage_plan"]
    shard = PRPreFlightASTWorker().build_shard(
        plan,
        _context("code", uncertainties=["caller graph partial"]),
    )
    assert shard["uncertainties"] == ["caller graph partial"]


def test_empty_context_still_emits_valid_shard():
    plan = _plan_for("FIXTURE-002-escalation.json")["coverage_plan"]
    shard = DocsDriftAndSpecWorker().build_shard(plan, None)
    assert shard["observations"] == ["no doc drift signal recorded in context"]
    jsonschema.validate(shard, SHARD_SCHEMA)
# ---------------------------------------------------------------------------
# Registry resolution.
# ---------------------------------------------------------------------------


def test_registry_returns_all_six_workers():
    registry = WorkerRegistry()
    assert len(registry.worker_names()) == 6
    for worker_cls in ALL_WORKER_CLASSES:
        instance = worker_cls()
        resolved = registry.get(instance.worker_name)
        assert isinstance(resolved, Worker)
        assert resolved.domain == instance.domain
        assert type(resolved) is worker_cls


def test_registry_rejects_unknown_worker():
    with pytest.raises(WorkerError, match="unknown worker"):
        WorkerRegistry().get("rogue-worker")


# ---------------------------------------------------------------------------
# Concurrent execution: the coordinator runs each selected worker per its own
# domain (FIXTURE-002 covers all three domains; FIXTURE-001 covers code only).
# ---------------------------------------------------------------------------


def test_coordinator_dispatches_all_three_mvp_workers_concurrently():
    plan = _plan_for("FIXTURE-002-escalation.json")["coverage_plan"]
    contexts = {
        "pr-pre-flight-ast-worker": {
            "domain": "code",
            "inputs": {"changed_files": ["auth/config.go"]},
        },
        "build-log-and-flakiness-worker": {
            "domain": "delivery",
            "inputs": {"ci_outcome": "pass"},
        },
        "telemetry-correlation-worker": {
            "domain": "production",
            "inputs": {"telemetry_signals": [12.5]},
        },
    }
    outcome = WorkerCoordinator().dispatch(plan, contexts)
    assert outcome["errors"] == {}
    assert len(outcome["shards"]) == 3
    domains = sorted(shard["domain"] for shard in outcome["shards"])
    assert domains == ["code", "delivery", "production"]
    for shard in outcome["shards"]:
        jsonschema.validate(shard, SHARD_SCHEMA)


def test_coordinator_rejects_worker_from_unselected_domain():
    plan = _plan_for("FIXTURE-001-happy-path.json")["coverage_plan"]  # code + production (ADR-014)
    outcome = WorkerCoordinator().dispatch(
        plan,
        {
            "pr-pre-flight-ast-worker": {"domain": "code", "inputs": {}},
            "build-log-and-flakiness-worker": {"domain": "delivery", "inputs": {}},
        },
    )
    # Only the selected-domain worker ran.
    assert [s["worker"] for s in outcome["shards"]] == ["pr-pre-flight-ast-worker"]
    assert "build-log-and-flakiness-worker" in outcome["errors"]
    assert "not selected for coverage" in outcome["errors"]["build-log-and-flakiness-worker"]