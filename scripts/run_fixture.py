#!/usr/bin/env python3
"""
ForgeMind Fixture Runner (Phase 0 baseline + Phase 1 acquisition).

Validates canonical Event-envelope fixtures against the machine-readable
JSON Schema contracts in specs/001-hierarchical-runtime-dag/contracts/.

Phase 0 scope: validates the Event envelope against event.schema.json and
cross-checks that every artifact listed in fixture.expected_artifacts is
covered by a group in the matching fixtures/expected/*-expected.json file.

Phase 1 scope (T100 — Contracts & Event Acquisition): additionally acquires
each fixture event through forgemind.acquisition.acquire_event() and
requires the produced CoveragePlan to be schema-valid against
coverage-plan.schema.json with an unbroken Event -> CoveragePlan lineage
(situation_id carried over; provenance references the exact upstream
event_id).  Acquisition is escalation-agnostic: FIXTURE-002 therefore also
produces a CoveragePlan here; escalation *semantics* remain Phase 6.

Phase 2 scope (T200 — Tier 1 Supervisor): additionally runs the Tier 1
Supervisor over the acquired CoveragePlan and verifies the resulting
SupervisorDispatch trace record: selected managers match the plan, the
CoveragePlan's global constraints are enforced, and provenance references
the upstream event_id and coverage_plan_id.  SupervisorDispatch is a
trace record, not a canonical artifact; manager execution remains Phase 3.

Usage:
    python scripts/run_fixture.py                                            # all fixtures
    python scripts/run_fixture.py fixtures/inputs/FIXTURE-001-happy-path.json
    python scripts/run_fixture.py --out var/artifacts fixtures/inputs/FIXTURE-001-happy-path.json
"""

import argparse
import json
import sys
from pathlib import Path

# Bootstrap: allow running as a standalone script with a src/ layout package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import jsonschema
except ImportError:
    sys.exit("Error: 'jsonschema' is required. Install with: uv sync")

from forgemind import CONTRACTS_DIR, FIXTURES_EXPECTED_DIR, FIXTURES_INPUT_DIR
from forgemind.acquisition import EventValidationError, acquire_event, persist_artifacts
from forgemind.supervisor import Supervisor, SupervisorError
from forgemind.domain_managers import DomainError, ManagerCoordinator
from forgemind.workers import WorkerCoordinator, WorkerError


def load_json(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def validate_fixture(fixture_path: Path, out_dir=None) -> int:
    """Validate one fixture. Returns the number of errors found."""
    fixture = load_json(fixture_path)
    fid = fixture.get("fixture_id", fixture_path.stem)
    errors = 0

    # 1) Event envelope must validate against the event contract.
    event_schema = CONTRACTS_DIR / "event.schema.json"
    try:
        jsonschema.validate(fixture.get("event", {}), load_json(event_schema))
        print(f"[ok] {fid}: event envelope passes event.schema.json")
    except jsonschema.ValidationError as exc:
        print(f"[FAIL] {fid}: event envelope vs event.schema.json -> {exc.message}")
        return 1

    # 2) Expected assertions must exist for this fixture.
    expected_file = FIXTURES_EXPECTED_DIR / f"{fid}-expected.json"
    if not expected_file.exists():
        print(f"[FAIL] {fid}: missing expected assertions file {expected_file.name}")
        return 1
    expected = load_json(expected_file)
    groups = {g.get("artifact") for g in expected.get("assertions", [])}
    print(f"[ok] {fid}: expected assertions present ({len(groups)} groups)")

    # 3) Cross-check: every artifact the fixture declares must be covered by an assertion group.
    for artifact in fixture.get("expected_artifacts", []):
        if artifact in groups:
            print(f"[ok] {fid}: artifact '{artifact}' covered by assertions")
        else:
            print(f"[FAIL] {fid}: expected artifact '{artifact}' not covered by assertions")
            errors += 1

    # 4) Phase 1 (T100): acquire the event; the produced CoveragePlan must be
    #    schema-valid with an unbroken Event -> CoveragePlan lineage prefix.
    try:
        acquired = acquire_event(fixture.get("event", {}))
    except EventValidationError as exc:
        print(f"[FAIL] {fid}: acquisition rejected event -> {exc}")
        return errors + 1

    plan = acquired["coverage_plan"]
    try:
        jsonschema.validate(
            plan, load_json(CONTRACTS_DIR / "coverage-plan.schema.json")
        )
        print(
            f"[ok] {fid}: CoveragePlan {plan['coverage_plan_id']} schema-valid "
            f"(trace={plan['execution_trace_id']}, "
            f"domains={plan['selected_domains']})"
        )
    except jsonschema.ValidationError as exc:
        print(f"[FAIL] {fid}: CoveragePlan vs coverage-plan.schema.json -> {exc.message}")
        errors += 1

    event = acquired["event"]
    lineage_ok = (
        plan.get("situation_id") == event.get("situation_id")
        and plan.get("provenance", {}).get("event_id") == event.get("event_id")
    )
    if lineage_ok:
        print(
            f"[ok] {fid}: lineage intact (situation_id={plan['situation_id']}, "
            f"provenance.event_id={event['event_id']})"
        )
    else:
        print(f"[FAIL] {fid}: CoveragePlan lineage broken")
        errors += 1

    # 5) Phase 2 (T200): run the Tier 1 Supervisor dispatch over the acquired
    #    CoveragePlan and validate the SupervisorDispatch trace record.
    try:
        dispatch = Supervisor().dispatch(plan)
    except SupervisorError as exc:
        print(f"[FAIL] {fid}: Supervisor rejected CoveragePlan -> {exc}")
        errors += 1
    else:
        prov = dispatch["provenance"]
        structure_ok = (
            dispatch["artifact_type"] == "SupervisorDispatch"
            and dispatch["execution_trace_id"] == plan["execution_trace_id"]
            and dispatch["situation_id"] == plan["situation_id"]
            and dispatch["coverage_plan_id"] == plan["coverage_plan_id"]
            and dispatch["selected_managers"] == plan["selected_managers"]
            and dispatch["global_constraints"] == plan["global_constraints"]
            and bool(dispatch["dispatch_rationale"])
            and prov["event_id"] == event["event_id"]
            and prov["coverage_plan_id"] == plan["coverage_plan_id"]
        )
        if structure_ok:
            print(
                f"[ok] {fid}: Supervisor dispatches "
                f"{dispatch['selected_managers']} (constraints enforced: "
                f"max_concurrent_managers="
                f"{dispatch['global_constraints']['max_concurrent_managers']}, "
                f"global_timeout_seconds="
                f"{dispatch['global_constraints']['global_timeout_seconds']}, "
                f"require_human_above_risk_level="
                f"{dispatch['global_constraints']['require_human_above_risk_level']!r})"
            )
            print(
                f"[ok] {fid}: dispatch provenance intact "
                f"(event_id={prov['event_id']}, "
                f"coverage_plan_id={prov['coverage_plan_id']})"
            )
        else:
            print(f"[FAIL] {fid}: SupervisorDispatch structure invalid")
            errors += 1

    # 6) Phase 3 (T300): if the fixture carries schema-valid EvidenceShards,
    #    run the CoveragePlan-selected Tier 2 Domain Managers over them and
    #    validate the emitted DomainFindings.  Absent evidence is fine for
    #    non-domain fixtures (FIXTURE-001/002) and does not count as an error.
    evidence_shards = fixture.get("evidence_shards")
    if evidence_shards:
        evidence_shard_schema = load_json(
            CONTRACTS_DIR / "evidence-shard.schema.json"
        )
        for index, shard in enumerate(evidence_shards):
            try:
                jsonschema.validate(shard, evidence_shard_schema)
            except jsonschema.ValidationError as exc:
                print(
                    f"[FAIL] {fid}: evidence_shards[{index}] vs "
                    f"evidence-shard.schema.json -> {exc.message}"
                )
                errors += 1

        coordinator = ManagerCoordinator()
        try:
            outcome = coordinator.dispatch(dispatch, plan, evidence_shards)
        except DomainError as exc:
            print(f"[FAIL] {fid}: Domain Manager coordinator rejected input -> {exc}")
            errors += 1
        else:
            findings = outcome["findings"]
            finding_schema = load_json(CONTRACTS_DIR / "domain-finding.schema.json")
            for domain in sorted(findings):
                finding = findings[domain]
                try:
                    jsonschema.validate(finding, finding_schema)
                except jsonschema.ValidationError as exc:
                    print(
                        f"[FAIL] {fid}: DomainFinding {finding.get('finding_id')} "
                        f"vs domain-finding.schema.json -> {exc.message}"
                    )
                    errors += 1
                    continue
                prov = finding["provenance"]
                structure_ok = (
                    finding["situation_id"] == dispatch["situation_id"]
                    and finding["domain"] == domain
                    and prov["event_id"] == event["event_id"]
                    and prov["coverage_plan_id"] == plan["coverage_plan_id"]
                    and prov["execution_trace_id"]
                    == plan["execution_trace_id"]
                    and finding["execution_trace_id"]
                    == plan["execution_trace_id"]
                )
                if structure_ok:
                    print(
                        f"[ok] {fid}: DomainFinding {finding['finding_id']} "
                        f"aggregates {len(finding['evidence_shard_ids'])} "
                        f"shard(s) in domain {domain} (confidence "
                        f"{finding['confidence']})"
                    )
                    print(
                        f"[ok] {fid}: {domain} provenance intact "
                        f"(event_id={prov['event_id']}, "
                        f"coverage_plan_id={prov['coverage_plan_id']}, "
                        f"execution_trace_id={prov['execution_trace_id']})"
                    )
                else:
                    print(f"[FAIL] {fid}: DomainFinding {finding.get('finding_id')} structure invalid")
                    errors += 1
            for rejected_note in outcome["rejected"]:
                print(f"[FAIL] {fid}: {rejected_note}")
                errors += 1
            for domain, message in sorted(outcome["errors"].items()):
                print(f"[FAIL] {fid}: {domain} manager failed -> {message}")
                errors += 1

    # 7) Phase 4 (T400): if the fixture carries per-worker context
    #    (the ``workers`` mapping), run the CoveragePlan-selected Tier 3
    #    Specialist Workers and validate the emitted EvidenceShards.  Absent
    #    worker context is fine for non-worker fixtures and does not count as
    #    an error.
    worker_contexts = fixture.get("workers")
    if worker_contexts:
        shard_schema = load_json(CONTRACTS_DIR / "evidence-shard.schema.json")
        worker_coordinator = WorkerCoordinator()
        try:
            worker_outcome = worker_coordinator.dispatch(plan, worker_contexts)
        except WorkerError as exc:
            print(f"[FAIL] {fid}: Worker coordinator rejected input -> {exc}")
            errors += 1
        else:
            for shard in worker_outcome["shards"]:
                try:
                    jsonschema.validate(shard, shard_schema)
                except jsonschema.ValidationError as exc:
                    print(
                        f"[FAIL] {fid}: EvidenceShard {shard.get('evidence_shard_id')} "
                        f"vs evidence-shard.schema.json -> {exc.message}"
                    )
                    errors += 1
                    continue
                prov = shard["provenance"]
                boundary_ok = (
                    shard["situation_id"] == plan["situation_id"]
                    and prov["event_id"] == event["event_id"]
                    and prov["coverage_plan_id"] == plan["coverage_plan_id"]
                    and prov["execution_trace_id"] == plan["execution_trace_id"]
                    and shard["execution_trace_id"] == plan["execution_trace_id"]
                    and not any(
                        key in shard
                        for key in (
                            "finding_id",
                            "validated_situation_id",
                            "decision_record_id",
                            "proposed_action_id",
                        )
                    )
                )
                if boundary_ok:
                    print(
                        f"[ok] {fid}: EvidenceShard {shard['evidence_shard_id']} "
                        f"emitted by {shard['worker']} in domain {shard['domain']} "
                        f"(confidence {shard['confidence']})"
                    )
                    print(
                        f"[ok] {fid}: {shard['worker']} provenance intact "
                        f"(event_id={prov['event_id']}, "
                        f"coverage_plan_id={prov['coverage_plan_id']}, "
                        f"execution_trace_id={prov['execution_trace_id']})"
                    )
                else:
                    print(
                        f"[FAIL] {fid}: EvidenceShard {shard.get('evidence_shard_id')} "
                        "structure invalid (provenance or boundary guard failed)"
                    )
                    errors += 1
            for worker_name, message in sorted(worker_outcome["errors"].items()):
                print(f"[FAIL] {fid}: {worker_name} worker failed -> {message}")
                errors += 1

    # 8) Optional durability demonstration (--out DIR).
    if out_dir is not None:
        for path in persist_artifacts(acquired, out_dir):
            print(f"[ok] {fid}: persisted {path}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ForgeMind fixture runner (Phase 0 contracts + Phase 1 acquisition)"
    )
    parser.add_argument("fixture", type=Path, nargs="?",
                        help="Path to a fixture JSON under fixtures/inputs/")
    parser.add_argument("--out", type=Path, default=None,
                        help="Persist acquired Event + CoveragePlan artifacts as "
                             "JSON under this directory (Phase 1 durability)")
    args = parser.parse_args()

    if args.fixture is not None:
        if not args.fixture.exists():
            sys.exit(f"Error: fixture not found: {args.fixture}")
        total = validate_fixture(args.fixture, out_dir=args.out)
    else:
        fixture_files = sorted(FIXTURES_INPUT_DIR.glob("*.json"))
        if not fixture_files:
            sys.exit("Error: no fixtures found in fixtures/inputs/")
        total = sum(validate_fixture(p, out_dir=args.out) for p in fixture_files)

    print(f"\nFixture validation complete. {total} error(s).")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
