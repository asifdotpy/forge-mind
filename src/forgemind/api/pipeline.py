from __future__ import annotations

"""Pure five-tier pipeline orchestration (no HTTP logic)."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from forgemind._paths import FIXTURES_INPUT_DIR
from forgemind.acquisition import acquire_event
from forgemind.action_gate import ActionValidationGate, publish_terminal_output
from forgemind.api.models import EventInput
from forgemind.domain_managers import ManagerCoordinator
from forgemind.m3_proof import build_m3_proof
from forgemind.reducer import DecisionReducer
from forgemind.supervisor import Supervisor
from forgemind.validator import CrossLifecycleValidator
from forgemind.workers import WorkerCoordinator

def run_pipeline(body: EventInput) -> Dict[str, Any]:
    """Drive one Event through the five-tier DAG and assemble the response.

    Pure orchestration of existing tiers — no new logic.  Raises the tiers'
    own error classes (:class:`EventValidationError`, :data:`PIPELINE_ERRORS`);
    HTTP mapping happens in the route handler.
    """
    # Acquire layer: normalize + validate against event.schema.json,
    # derive execution_trace_id / coverage_plan_id deterministically.
    acquired = acquire_event(body.event)
    event = acquired["event"]
    plan = acquired["coverage_plan"]

    # Tier 1 — Engineering Supervisor: constraint enforcement + dispatch trace.
    supervisor_dispatch = Supervisor().dispatch(plan)

    # Tier 3 — Specialist Workers (optional): emit durable EvidenceShards.
    shards: List[Dict[str, Any]] = list(body.evidence_shards or [])
    if body.workers:
        worker_outcome = WorkerCoordinator().dispatch(plan, body.workers)
        shards.extend(worker_outcome["shards"])
    else:
        # Change 2: derive deterministic contexts from the event payload so a
        # raw event is self-sufficient (no hand-rolled workers key required).
        from forgemind.worker_contexts import build_worker_contexts

        derived = build_worker_contexts(event, plan)
        if derived:
            worker_outcome = WorkerCoordinator().dispatch(plan, derived)
            shards.extend(worker_outcome["shards"])

    # Tier 2 — Domain Managers: aggregate shards into bounded DomainFindings.
    findings_by_domain: Dict[str, Dict[str, Any]] = {}
    if shards:
        manager_outcome = ManagerCoordinator().dispatch(
            supervisor_dispatch, plan, shards
        )
        findings_by_domain = manager_outcome["findings"]

    # Tier 4 — Cross-Lifecycle Validator.  ALWAYS reconciles: an empty finding
    # set is the honest zero-confidence, coverage-gapped picture and MUST
    # escalate downstream (never act) — mirroring the FIXTURE-002 semantics.
    if body.domain_findings is not None:
        domain_findings = list(body.domain_findings)
    else:
        domain_findings = [
            findings_by_domain[domain] for domain in sorted(findings_by_domain)
        ]
    validated = CrossLifecycleValidator().validate(
        plan, domain_findings, shards or None
    )

    # Tier 5 — Decision Reducer: deterministic autonomy ladder.
    reduction = DecisionReducer().reduce(validated)
    decision_record = reduction["decision_record"]

    if reduction["proposed_action"] is not None:
        # Downstream safety gate, then the structural no-bypass publish point.
        gated = ActionValidationGate().validate(
            reduction["proposed_action"],
            decision_record,
            event_timestamp=event["timestamp"],
        )
        published = publish_terminal_output(
            gated["proposed_action"],
            gated["action_validation"],
            situation_id=plan["situation_id"],
            evidence_ids=validated.get("evidence_ids") or [],
        )
        terminal: Dict[str, Any] = {
            "type": published["terminal"],
            "decision_record": decision_record,
            "proposed_action": published["action"],
            "action_validation": gated["action_validation"],
            "escalation": published["escalation"],
        }
    else:
        # A reducer-produced Escalation is already terminal (human required);
        # publish_terminal_output only accepts gated ProposedActions.
        terminal = {
            "type": "escalation",
            "decision_record": decision_record,
            "proposed_action": None,
            "action_validation": None,
            "escalation": reduction["escalation"],
        }

    result: Dict[str, Any] = {
        "status": "ok",
        "situation_id": plan["situation_id"],
        "trace_id": plan["execution_trace_id"],
        "terminal": terminal,
        "artifacts": {
            "coverage_plan": plan,
            "supervisor_dispatch": supervisor_dispatch,
            "evidence_shards": shards,
            "domain_findings": domain_findings,
            "validated_situation": validated,
        },
    }
    # M3-A (T720): additive, presentation-only projection of the result into
    # the four judge-visible properties.  No tier logic is involved.
    result["m3_proof"] = build_m3_proof(result)
    return result


def _fixture_body_for(situation_id: str) -> Optional[EventInput]:
    """Find a repository fixture whose Event carries ``situation_id``.

    The runtime is stateless (no artifact store), so ``GET
    /api/v1/situations/{id}`` re-derives the situation by replaying the
    matching canonical fixture input.  Returns ``None`` when nothing matches.
    """
    for path in sorted(FIXTURES_INPUT_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # pragma: no cover - corrupt fixture
            continue
        event = payload.get("event")
        if isinstance(event, dict) and event.get("situation_id") == situation_id:
            return EventInput(**payload)
    return None
