"""Contract tests: Phase 1 event acquisition (SPEC-001 T100).

Exit criterion under test: one event is accepted as a durable,
schema-valid artifact, preserving the canonical lineage prefix
``Event -> CoveragePlan`` with replay-stable identifiers.

Canonical inputs: fixtures/inputs/FIXTURE-001-happy-path.json (happy
path) and fixtures/inputs/FIXTURE-002-escalation.json (escalation-path
event; acquisition is escalation-agnostic — escalation semantics are
Phase 6).
"""

import json

import jsonschema
import pytest

from forgemind import CONTRACTS_DIR, FIXTURES_INPUT_DIR
from forgemind.acquisition import (
    EventValidationError,
    acquire_event,
    persist_artifacts,
)

FORMAT_CHECKER = jsonschema.FormatChecker()
EVENT_SCHEMA = json.loads(
    (CONTRACTS_DIR / "event.schema.json").read_text(encoding="utf-8")
)
COVERAGE_PLAN_SCHEMA = json.loads(
    (CONTRACTS_DIR / "coverage-plan.schema.json").read_text(encoding="utf-8")
)


def _fixture_001_event():
    data = json.loads(
        (FIXTURES_INPUT_DIR / "FIXTURE-001-happy-path.json").read_text(
            encoding="utf-8"
        )
    )
    return data["event"]


@pytest.fixture(scope="module")
def acquired_001():
    return acquire_event(_fixture_001_event())


# ---------------------------------------------------------------------------
# Schema conformance (exit criterion)
# ---------------------------------------------------------------------------


def test_fixture_001_event_is_schema_valid(acquired_001):
    jsonschema.validate(
        acquired_001["event"], EVENT_SCHEMA, format_checker=FORMAT_CHECKER
    )
    assert acquired_001["event"]["event_id"] == "EVT-1000"


def test_fixture_001_coverage_plan_is_schema_valid(acquired_001):
    jsonschema.validate(acquired_001["coverage_plan"], COVERAGE_PLAN_SCHEMA)


# ---------------------------------------------------------------------------
# Idempotency / determinism
# ---------------------------------------------------------------------------


def test_acquisition_is_idempotent_across_replays():
    event = _fixture_001_event()
    first = acquire_event(event)
    second = acquire_event(dict(event))
    assert first == second


def test_identifiers_are_stable_pure_functions_of_event_id(acquired_001):
    assert acquired_001["execution_trace_id"] == "TRC-1000"
    assert acquired_001["coverage_plan"]["coverage_plan_id"] == "CP-1000"
    assert acquired_001["coverage_plan"]["execution_trace_id"] == "TRC-1000"


def test_explicit_trace_id_override_is_accepted_when_well_formed():
    acquired = acquire_event(
        _fixture_001_event(), execution_trace_id="TRC-custom-42"
    )
    assert acquired["execution_trace_id"] == "TRC-custom-42"
    assert acquired["coverage_plan"]["execution_trace_id"] == "TRC-custom-42"


def test_malformed_trace_id_override_is_rejected():
    with pytest.raises(EventValidationError, match="TRC-"):
        acquire_event(_fixture_001_event(), execution_trace_id="bogus-trace")


# ---------------------------------------------------------------------------
# Lineage & provenance (data-model.md Invariant 7)
# ---------------------------------------------------------------------------


def test_lineage_situation_and_provenance_intact(acquired_001):
    event, plan = acquired_001["event"], acquired_001["coverage_plan"]
    assert plan["situation_id"] == event["situation_id"] == "SIT-1000"
    assert plan["provenance"]["event_id"] == event["event_id"]


def test_original_provenance_preserved_verbatim(acquired_001):
    assert acquired_001["event"]["provenance"] == _fixture_001_event()["provenance"]


# ---------------------------------------------------------------------------
# CoveragePlan derivation (deterministic)
# ---------------------------------------------------------------------------


def test_pr_event_defaults_to_code_domain(acquired_001):
    plan = acquired_001["coverage_plan"]
    assert plan["selected_domains"] == ["code"]
    assert plan["selected_managers"] == ["code-intelligence-manager"]
    assert plan["selected_workers"] == [
        "pr-pre-flight-ast-worker",
        "docs-drift-and-spec-worker",
    ]
    assert plan["excluded_workers"] == [
        "build-log-and-flakiness-worker",
        "alert-storm-clustering-worker",
        "telemetry-correlation-worker",
        "security-and-dependency-worker",
    ]
    assert plan["selection_rationale"], "rationale must document the derivation"


def test_worker_partition_is_complete_and_disjoint(acquired_001):
    plan = acquired_001["coverage_plan"]
    all_workers = set(plan["selected_workers"]) | set(plan["excluded_workers"])
    assert (
        len(plan["selected_workers"]) + len(plan["excluded_workers"])
        == len(all_workers)
    )
    assert all_workers == {
        "pr-pre-flight-ast-worker",
        "docs-drift-and-spec-worker",
        "build-log-and-flakiness-worker",
        "alert-storm-clustering-worker",
        "telemetry-correlation-worker",
        "security-and-dependency-worker",
    }


def test_fixture_002_payload_domains_override_type_default():
    data = json.loads(
        (FIXTURES_INPUT_DIR / "FIXTURE-002-escalation.json").read_text(
            encoding="utf-8"
        )
    )
    acquired = acquire_event(data["event"])
    assert acquired["execution_trace_id"] == "TRC-2000"
    assert acquired["coverage_plan"]["selected_domains"] == [
        "code",
        "delivery",
        "production",
    ]


# ---------------------------------------------------------------------------
# Normalization (Acquire Layer order: Normalize · Validate)
# ---------------------------------------------------------------------------


def test_timestamp_normalized_to_canonical_utc_z():
    shifted = dict(_fixture_001_event(), timestamp="2026-08-21T11:00:00+02:00")
    acquired = acquire_event(shifted)
    assert acquired["event"]["timestamp"] == "2026-08-21T09:00:00Z"


def test_source_normalized_trimmed_and_lowercased_before_validation():
    noisy = dict(_fixture_001_event(), source="  GitHub ")
    acquired = acquire_event(noisy)
    assert acquired["event"]["source"] == "github"


# ---------------------------------------------------------------------------
# Rejection paths (raised from acquire_event itself, per review note N6)
# ---------------------------------------------------------------------------


def test_missing_required_field_is_rejected():
    broken = _fixture_001_event()
    del broken["reference"]
    with pytest.raises(EventValidationError, match="required"):
        acquire_event(broken)


def test_bad_event_id_pattern_is_rejected():
    with pytest.raises(EventValidationError, match="PR-1234"):
        acquire_event(dict(_fixture_001_event(), event_id="PR-1234"))


def test_unknown_source_enum_is_rejected():
    with pytest.raises(EventValidationError, match="slack"):
        acquire_event(dict(_fixture_001_event(), source="slack"))


def test_malformed_timestamp_rejected_in_production_path():
    for bad in ("not-a-timestamp", "2026-13-45T09:00:00Z"):
        with pytest.raises(EventValidationError, match="timestamp"):
            acquire_event(dict(_fixture_001_event(), timestamp=bad))
    with pytest.raises(EventValidationError, match="timezone"):
        acquire_event(dict(_fixture_001_event(), timestamp="2026-08-21T09:00:00"))


def test_non_object_event_is_rejected():
    with pytest.raises(EventValidationError, match="JSON object"):
        acquire_event(["not", "an", "object"])


# ---------------------------------------------------------------------------
# Durability (persist + independent re-validation round trip)
# ---------------------------------------------------------------------------


def test_persist_artifacts_roundtrip_revalidates(tmp_path):
    acquired = acquire_event(_fixture_001_event())
    paths = {p.name: p for p in persist_artifacts(acquired, tmp_path)}
    assert set(paths) == {"EVT-1000.event.json", "EVT-1000.coverage-plan.json"}

    event = json.loads(paths["EVT-1000.event.json"].read_text(encoding="utf-8"))
    plan = json.loads(
        paths["EVT-1000.coverage-plan.json"].read_text(encoding="utf-8")
    )

    assert event == acquired["event"]
    assert plan == acquired["coverage_plan"]
    jsonschema.validate(event, EVENT_SCHEMA, format_checker=FORMAT_CHECKER)
    jsonschema.validate(plan, COVERAGE_PLAN_SCHEMA)
