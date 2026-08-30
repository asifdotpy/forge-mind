"""ADK 2.0 tool functions for the ForgeMind five-tier DAG.

Each tool follows the canonical ADK 2.0 pattern: read inputs from
``tool_context.state``, call the existing deterministic tier function,
write outputs back to ``tool_context.state``, and return the actual result
dict so the LLM agent can reference it.

These tools are attached to ``LlmAgent`` wrappers in
:func:`forgemind.agents.root_agent.build_runner_root_agent` and executed
via ``Runner.run_async()``.

All ``google.adk`` imports are lazy (inside function bodies) per ADR-009:
``import forgemind.tools.adk_tools`` must succeed without ``google-adk``
installed.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "call_supervisor",
    "call_workers",
    "call_managers",
    "call_validator",
    "call_reducer",
    "call_action_gate",
]


def call_supervisor(tool_context: Any) -> dict:
    """Tier 1: Dispatch event through the Engineering Supervisor.

    Reads ``coverage_plan`` from state, writes ``supervisor_dispatch``.
    """
    from forgemind.supervisor import Supervisor

    plan = tool_context.state["coverage_plan"]
    supervisor_dispatch = Supervisor().dispatch(plan)
    tool_context.state["supervisor_dispatch"] = supervisor_dispatch
    return supervisor_dispatch


def call_workers(tool_context: Any) -> dict:
    """Tier 3: Run specialist workers to produce EvidenceShards.

    Reads ``coverage_plan``, ``event``, and optional ``workers``/``evidence_shards`` from state.
    Writes ``evidence_shards`` (list of shard dicts).
    """
    from forgemind.worker_contexts import build_worker_contexts
    from forgemind.workers import WorkerCoordinator

    plan = tool_context.state["coverage_plan"]
    event = tool_context.state["event"]

    shards: list = list(tool_context.state.get("evidence_shards") or [])
    workers = tool_context.state.get("workers")
    if workers:
        worker_outcome = WorkerCoordinator().dispatch(plan, workers)
        shards.extend(worker_outcome["shards"])
    else:
        derived = build_worker_contexts(event, plan)
        if derived:
            worker_outcome = WorkerCoordinator().dispatch(plan, derived)
            shards.extend(worker_outcome["shards"])

    tool_context.state["evidence_shards"] = shards
    return {"shards": shards, "count": len(shards)}


def call_managers(tool_context: Any) -> dict:
    """Tier 2: Aggregate EvidenceShards into per-domain DomainFindings.

    Reads ``supervisor_dispatch``, ``coverage_plan``, ``evidence_shards``,
    and optional pre-set ``domain_findings``.
    Writes ``domain_findings`` (list of finding dicts).
    """
    if tool_context.state.get("domain_findings") is not None:
        domain_findings = list(tool_context.state["domain_findings"])
        return {"domain_findings": domain_findings, "count": len(domain_findings)}

    from forgemind.domain_managers import ManagerCoordinator

    supervisor_dispatch = tool_context.state["supervisor_dispatch"]
    plan = tool_context.state["coverage_plan"]
    shards = tool_context.state.get("evidence_shards") or []

    findings_by_domain: dict = {}
    if shards:
        manager_outcome = ManagerCoordinator().dispatch(
            supervisor_dispatch, plan, shards
        )
        findings_by_domain = manager_outcome["findings"]

    domain_findings = [
        findings_by_domain[domain] for domain in sorted(findings_by_domain)
    ]
    tool_context.state["domain_findings"] = domain_findings
    return {"domain_findings": domain_findings, "count": len(domain_findings)}


def call_validator(tool_context: Any) -> dict:
    """Tier 4: Reconcile DomainFindings into a ValidatedSituation.

    Reads ``coverage_plan``, ``domain_findings``, ``evidence_shards``,
    ``repo``, ``sha``.
    Writes ``validated_situation``.
    """
    from forgemind.validator import CrossLifecycleValidator

    plan = tool_context.state["coverage_plan"]
    domain_findings = tool_context.state.get("domain_findings") or []
    shards = tool_context.state.get("evidence_shards") or []
    repo = tool_context.state.get("repo", "")
    sha = tool_context.state.get("sha", "")

    validated = CrossLifecycleValidator().validate(
        plan, domain_findings, shards or None, repo=repo, sha=sha
    )
    tool_context.state["validated_situation"] = validated
    return validated


def call_reducer(tool_context: Any) -> dict:
    """Tier 5: Reduce the ValidatedSituation into a decision.

    Reads ``validated_situation``.
    Writes ``decision_record``, ``proposed_action``, ``escalation``.
    """
    from forgemind.reducer import DecisionReducer

    validated = tool_context.state["validated_situation"]
    reduction = DecisionReducer().reduce(validated)

    tool_context.state["decision_record"] = reduction["decision_record"]
    tool_context.state["proposed_action"] = reduction["proposed_action"]
    tool_context.state["escalation"] = reduction["escalation"]
    return reduction


def call_action_gate(tool_context: Any) -> dict:
    """Action Validation Gate + pause/resume.

    Reads ``proposed_action``, ``decision_record``, ``event_timestamp``.
    Writes ``terminal`` and optionally ``pending_approval``.

    When the gate decides ``requires_human``, the action is NOT published.
    Instead, the workflow state receives a ``pending_approval`` token and
    the paused context is written to ``_PENDING_APPROVALS`` (same store as
    the deterministic ADK path) for later resume via
    ``POST /api/v1/approvals/{token}``.
    """
    import uuid

    from forgemind.action_gate import (
        ActionValidationGate,
        publish_terminal_output,
    )
    from forgemind.adk_runtime import _PENDING_APPROVALS

    proposed_action = tool_context.state.get("proposed_action")
    decision_record = tool_context.state["decision_record"]
    event_timestamp = tool_context.state.get("event_timestamp", "")

    if proposed_action is None:
        # Reducer-produced Escalation — already terminal.
        terminal = {
            "type": "escalation",
            "decision_record": decision_record,
            "proposed_action": None,
            "action_validation": None,
            "escalation": tool_context.state.get("escalation"),
        }
        tool_context.state["terminal"] = terminal
        tool_context.state["pending_approval"] = None
        return terminal

    gated = ActionValidationGate().validate(
        proposed_action,
        decision_record,
        event_timestamp=event_timestamp,
    )

    if gated.get("action_validation", {}).get("policy_result") == "requires_human":
        # Pause: write to the shared approval store.
        token = uuid.uuid4().hex
        plan = tool_context.state["coverage_plan"]
        validated = tool_context.state["validated_situation"]
        shards = tool_context.state.get("evidence_shards") or []
        domain_findings = tool_context.state.get("domain_findings") or []

        _PENDING_APPROVALS[token] = {
            "plan": plan,
            "supervisor_dispatch": tool_context.state["supervisor_dispatch"],
            "shards": shards,
            "domain_findings": domain_findings,
            "validated": validated,
            "gated": gated,
            "event_timestamp": event_timestamp,
        }

        pending_approval = {
            "token": token,
            "decision_required": True,
            "resume_endpoint": f"/api/v1/approvals/{token}",
            "summary": (
                "Action requires human approval before publishing "
                f"(policy_result='requires_human', risk_level="
                f"'{decision_record.get('risk_level')}')."
            ),
        }
        tool_context.state["terminal"] = None
        tool_context.state["pending_approval"] = pending_approval
        tool_context.state["action_validation"] = gated["action_validation"]
        return {
            "status": "paused",
            "pending_approval": pending_approval,
        }

    # No human required: publish through the structural no-bypass point.
    validated = tool_context.state["validated_situation"]
    plan = tool_context.state["coverage_plan"]
    published = publish_terminal_output(
        gated["proposed_action"],
        gated["action_validation"],
        situation_id=plan["situation_id"],
        evidence_ids=validated.get("evidence_ids") or [],
    )
    terminal = {
        "type": published["terminal"],
        "decision_record": decision_record,
        "proposed_action": published["action"],
        "action_validation": gated["action_validation"],
        "escalation": published["escalation"],
    }
    tool_context.state["terminal"] = terminal
    tool_context.state["pending_approval"] = None
    return terminal
