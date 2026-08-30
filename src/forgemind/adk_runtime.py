"""ADK 2-style workflow wrapper around the five-tier DAG (M3-B / ADR-010).

This module realises the ADK 2 orchestration contract (explicit, named,
pause/resume-capable stages) over the EXISTING deterministic tiers.  It does
NOT re-implement any tier logic: every node calls the same functions
``forgemind.api.run_pipeline`` already calls, in the same order, so the
deterministic (``FORGEMIND_RUNTIME=deterministic``) path is byte-for-byte
unaffected and the 133-test suite stays green.

Only two things are ADK-specific here:

1. The DAG is made EXPLICIT as an ordered list of named nodes
   (:data:`ADK_WORKFLOW_NODES`) so the ADK 2 "workflow graph" is visible and
   testable rather than implicit in one big function.
2. A ``human_approval`` node is inserted between ``reducer`` and
   ``action_gate``.  When the downstream gate decides an action
   ``requires_human`` (the reducer's ``requires_human`` ladder, surfaced by
   the Action Validation gate), the workflow PAUSES with a
   ``pending_approval`` token instead of publishing.  The terminal outcome is
   only produced when a human resumes the workflow via
   :func:`resume_adk_pipeline` (approve -> publish; reject -> escalation).

No Google ``google.adk`` dependency is required at import time: the workflow
is a self-contained, stdlib-only realisation of the ADK 2 Sequential/Workflow
semantics, which keeps ``import forgemind.adk_runtime`` working offline and
the ADR-009 import-boundary test green.  The GenAI SDK (``google-genai``) is
used only lazily, inside ``forgemind.llm.adapter``.

Activation: the ADK path is inert unless ``FORGEMIND_RUNTIME=adk``.  The
default ``deterministic`` runtime never enters this module.
"""

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from forgemind.acquisition import EventValidationError, acquire_event
from forgemind.action_gate import (
    ActionGateError,
    ActionValidationGate,
    publish_terminal_output,
)
from forgemind.domain_managers import DomainManagerError, ManagerCoordinator
from forgemind.m3_proof import build_m3_proof
from forgemind.reducer import DecisionReducer, ReducerError
from forgemind.supervisor import Supervisor, SupervisorError
from forgemind.validator import CrossLifecycleValidator, ValidatorError
from forgemind.workers import WorkerCoordinator, WorkerError

__all__ = [
    "ADK_WORKFLOW_NODES",
    "FORGEMIND_RUNTIME_ENV",
    "ADK_RUNTIME_VALUE",
    "ADK_RUNNER_RUNTIME_VALUE",
    "is_adk_runtime",
    "is_adk_runner_runtime",
    "describe_adk_workflow",
    "run_adk_pipeline",
    "run_adk_runner_pipeline",
    "run_adk_runner_pipeline_async",
    "resume_adk_pipeline",
    "ApprovalError",
]

#: Environment flag selecting the runtime.
FORGEMIND_RUNTIME_ENV = "FORGEMIND_RUNTIME"
ADK_RUNTIME_VALUE = "adk"
ADK_RUNNER_RUNTIME_VALUE = "adk+runner"

#: The explicit ADK 2 workflow graph.  Each node maps 1:1 to an existing tier
#: function; the human_approval node is the only ADK-native addition.
ADK_WORKFLOW_NODES = (
    "acquire",
    "supervisor",
    "workers",
    "managers",
    "validator",
    "reducer",
    "human_approval",  # ADK pause/resume gate (no-op for autonomous actions)
    "action_gate",
)


def is_adk_runner_runtime() -> bool:
    """True only when ``FORGEMIND_RUNTIME=adk+runner``."""
    return os.environ.get(FORGEMIND_RUNTIME_ENV, "deterministic").lower() == (
        ADK_RUNNER_RUNTIME_VALUE
    )


def is_adk_runtime() -> bool:
    """True when ``FORGEMIND_RUNTIME=adk`` or ``FORGEMIND_RUNTIME=adk+runner``."""
    val = os.environ.get(FORGEMIND_RUNTIME_ENV, "deterministic").lower()
    return val in (ADK_RUNTIME_VALUE, ADK_RUNNER_RUNTIME_VALUE)


def describe_adk_workflow() -> tuple:
    """Return the ordered ADK 2 node names (for docs / tests)."""
    return tuple(ADK_WORKFLOW_NODES)


class ApprovalError(ValueError):
    """A human-approval resume was requested for an unknown/missing token."""


# -- in-memory pause store ------------------------------------------------
# The runtime is otherwise stateless (no artifact store); the only state we
# keep is the set of PAUSED workflows awaiting a human decision.  Tokens are
# opaque UUIDs; nothing here is persisted across process restarts (this is a
# demo affordance, not a durable job store).
_PENDING_APPROVALS: Dict[str, Dict[str, Any]] = {}


def _needs_human_approval(gated: Dict[str, Any]) -> bool:
    """True when the gate withheld the action for a human (requires_human)."""
    return bool(
        gated.get("action_validation", {}).get("policy_result") == "requires_human"
    )


def _assemble_result(
    *,
    plan: dict,
    supervisor_dispatch: dict,
    shards: List[dict],
    domain_findings: List[dict],
    validated: dict,
    terminal: Optional[dict],
    status: str = "ok",
    human_decision: Optional[str] = None,
    pending_approval: Optional[dict] = None,
    decision_record: Optional[dict] = None,
    action_validation: Optional[dict] = None,
) -> dict:
    """Build the pipeline-shaped result (mirrors ``api.run_pipeline``)."""
    result: Dict[str, Any] = {
        "status": status,
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
    if decision_record is not None:
        result["decision_record"] = decision_record
    if action_validation is not None:
        result["action_validation"] = action_validation
    if pending_approval is not None:
        result["pending_approval"] = pending_approval
    if human_decision is not None:
        result["human_decision"] = human_decision
    # M3-A (T720): additive, presentation-only projection (no tier logic).
    result["m3_proof"] = build_m3_proof(result)
    return result


def run_adk_pipeline(body: Any) -> Dict[str, Any]:
    """Drive one Event through the ADK 2 workflow graph.

    Pure orchestration of the existing tiers — identical to
    ``forgemind.api.run_pipeline`` for the non-paused path.  The only added
    branch is the ``human_approval`` node, which PAUSES (instead of
    publishing) whenever the Action Validation gate decides the proposed
    action ``requires_human``.

    Raises the tiers' own error classes (same as ``run_pipeline``); the API
    layer maps them to HTTP responses.
    """
    # Node: acquire
    acquired = acquire_event(body.event)
    event = acquired["event"]
    plan = acquired["coverage_plan"]

    # Node: supervisor
    supervisor_dispatch = Supervisor().dispatch(plan)

    # Node: workers (optional, bounded to selected domains)
    shards: List[Dict[str, Any]] = list(body.evidence_shards or [])
    if body.workers:
        worker_outcome = WorkerCoordinator().dispatch(plan, body.workers)
        shards.extend(worker_outcome["shards"])
    else:
        # Change 2: derive deterministic contexts from the event payload so a
        # raw event is self-sufficient (no hand-rolled workers key required).
        # Mirrors api.run_pipeline to preserve deterministic<->ADK parity.
        from forgemind.worker_contexts import build_worker_contexts

        derived = build_worker_contexts(event, plan)
        if derived:
            worker_outcome = WorkerCoordinator().dispatch(plan, derived)
            shards.extend(worker_outcome["shards"])

    # Node: managers (aggregate shards into DomainFindings)
    findings_by_domain: Dict[str, Dict[str, Any]] = {}
    if shards:
        manager_outcome = ManagerCoordinator().dispatch(
            supervisor_dispatch, plan, shards
        )
        findings_by_domain = manager_outcome["findings"]

    # Node: validator (reconcile findings into a ValidatedSituation)
    if body.domain_findings is not None:
        domain_findings = list(body.domain_findings)
    else:
        domain_findings = [
            findings_by_domain[domain] for domain in sorted(findings_by_domain)
        ]
    payload = event.get("payload") or {}
    repo = str(payload.get("repo") or "")
    sha = str(payload.get("sha") or "")
    validated = CrossLifecycleValidator().validate(
        plan, domain_findings, shards or None, repo=repo, sha=sha
    )

    # Node: reducer (deterministic autonomy ladder -> decision)
    reduction = DecisionReducer().reduce(validated)
    decision_record = reduction["decision_record"]

    # Node: human_approval + action_gate
    if reduction["proposed_action"] is not None:
        gated = ActionValidationGate().validate(
            reduction["proposed_action"],
            decision_record,
            event_timestamp=event["timestamp"],
        )

        # ADK pause/resume gate: only block when the gate needs a human.
        if _needs_human_approval(gated):
            token = uuid.uuid4().hex
            pending = {
                "plan": plan,
                "supervisor_dispatch": supervisor_dispatch,
                "shards": shards,
                "domain_findings": domain_findings,
                "validated": validated,
                "gated": gated,
                "event_timestamp": event["timestamp"],
            }
            _PENDING_APPROVALS[token] = pending
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
            return _assemble_result(
                plan=plan,
                supervisor_dispatch=supervisor_dispatch,
                shards=shards,
                domain_findings=domain_findings,
                validated=validated,
                terminal=None,
                status="paused",
                pending_approval=pending_approval,
                decision_record=decision_record,
                action_validation=gated["action_validation"],
            )

        # No human required -> publish through the structural no-bypass point.
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

    return _assemble_result(
        plan=plan,
        supervisor_dispatch=supervisor_dispatch,
        shards=shards,
        domain_findings=domain_findings,
        validated=validated,
        terminal=terminal,
    )


async def run_adk_runner_pipeline_async(
    body: Any, session_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Drive one Event through the ADK 2.0 Runner via tool calling over session state.

    Returns the assembled pipeline-shaped result, or None if google-adk is unavailable
    or execution encounters an error requiring fallback.
    """
    from forgemind.adk_app import create_adk_tool_runner, is_adk_available

    if not is_adk_available():
        return None

    try:
        runner = create_adk_tool_runner()
    except Exception as exc:
        logger.warning("Failed to create ADK tool runner (%s); falling back", exc)
        return None

    if runner is None:
        return None

    acquired = acquire_event(body.event)
    event = acquired["event"]
    plan = acquired["coverage_plan"]
    payload = event.get("payload") or {}
    repo = str(payload.get("repo") or "")
    sha = str(payload.get("sha") or "")
    event_timestamp = str(event.get("timestamp") or "")

    sid = session_id or uuid.uuid4().hex

    initial_state = {
        "event": event,
        "coverage_plan": plan,
        "repo": repo,
        "sha": sha,
        "event_timestamp": event_timestamp,
        "workers": body.workers,
        "evidence_shards": list(body.evidence_shards or []),
        "domain_findings": list(body.domain_findings) if body.domain_findings is not None else None,
    }

    import inspect
    from google.genai import types

    user_msg = types.Content(
        role="user",
        parts=[types.Part.from_text(text=f"Process event {event.get('event_id', '')}")],
    )

    try:
        create_fn = runner.session_service.create_session
        if inspect.iscoroutinefunction(create_fn):
            await create_fn(
                app_name=runner.app_name,
                user_id="anonymous",
                session_id=sid,
                state=initial_state,
            )
        else:
            create_fn(
                app_name=runner.app_name,
                user_id="anonymous",
                session_id=sid,
                state=initial_state,
            )

        async for _ in runner.run_async(
            user_id="anonymous",
            session_id=sid,
            new_message=user_msg,
        ):
            pass

        get_fn = runner.session_service.get_session
        if inspect.iscoroutinefunction(get_fn):
            sess = await get_fn(
                app_name=runner.app_name,
                user_id="anonymous",
                session_id=sid,
            )
        else:
            sess = get_fn(
                app_name=runner.app_name,
                user_id="anonymous",
                session_id=sid,
            )
        final_state = sess.state if sess else {}
    except Exception as exc:
        logger.warning(
            "ADK runner execution failed for session %s (%s); falling back",
            sid,
            exc,
        )
        return None

    if "validated_situation" not in final_state or "supervisor_dispatch" not in final_state:
        logger.warning(
            "ADK runner completed without populating pipeline state for session %s; falling back",
            sid,
        )
        return None

    status = "paused" if final_state.get("pending_approval") else "ok"
    return _assemble_result(
        plan=plan,
        supervisor_dispatch=final_state["supervisor_dispatch"],
        shards=final_state.get("evidence_shards") or [],
        domain_findings=final_state.get("domain_findings") or [],
        validated=final_state["validated_situation"],
        terminal=final_state.get("terminal"),
        status=status,
        pending_approval=final_state.get("pending_approval"),
        decision_record=final_state.get("decision_record"),
        action_validation=final_state.get("action_validation"),
    )


def run_adk_runner_pipeline(
    body: Any, session_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Synchronous entry point for the ADK 2.0 Runner tool execution path."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(
                lambda: asyncio.run(run_adk_runner_pipeline_async(body, session_id))
            ).result()
    else:
        return asyncio.run(run_adk_runner_pipeline_async(body, session_id))


def resume_adk_pipeline(
    token: str, 
    decision: str, 
    user_comment: str = "",
) -> Dict[str, Any]:
    """Resume a PAUSED workflow after a human decision.

    Args:
        token: the opaque ``pending_approval.token`` from a paused run.
        decision: ``"approve"`` (proceed to publish the gated outcome) or
            ``"reject"`` (record an Escalation, publish no action).
        user_comment: Optional reviewer feedback to attach to the result.

    Returns:
        The same pipeline-shaped result as :func:`run_adk_pipeline` would have
        returned had it published immediately, augmented with
        ``human_decision`` and optionally ``human_comment``.

    Raises:
        ApprovalError: the token is unknown / already consumed.
    """
    pending = _PENDING_APPROVALS.pop(token, None)
    if pending is None:
        raise ApprovalError(
            f"unknown or already-resolved approval token {token!r}; the "
            "workflow is not paused or was already resumed"
        )

    plan = pending["plan"]
    validated = pending["validated"]
    gated = pending["gated"]
    decision = (decision or "").lower()

    if decision == "approve":
        # Proceed through the structural no-bypass publish point (gate verdict
        # stands; for a requires_human action this is an Escalation terminal).
        published = publish_terminal_output(
            gated["proposed_action"],
            gated["action_validation"],
            situation_id=plan["situation_id"],
            evidence_ids=validated.get("evidence_ids") or [],
        )
        terminal: Dict[str, Any] = {
            "type": published["terminal"],
            "decision_record": _decision_record_from_pending(pending),
            "proposed_action": published["action"],
            "action_validation": gated["action_validation"],
            "escalation": published["escalation"],
        }
    elif decision == "reject":
        # Human veto: emit an Escalation (action_gate escalation shape), no
        # action published.  Reason stays within the contract enum; the
        # summary records the human veto explicitly.
        suffix = str(plan["situation_id"])
        for prefix in ("SIT-", "EVT-"):
            if suffix.startswith(prefix):
                suffix = suffix[len(prefix):]
                break
        escalation = {
            "escalation_id": f"ESC-{suffix}",
            "situation_id": plan["situation_id"],
            "reason": "policy_boundary",
            "summary": (
                "Human reviewer rejected the proposed action at the ADK "
                f"approval gate ({gated['action_validation']['validation_id']}); "
                "no terminal action was published."
            ),
            "required_human_role": "engineering-on-call",
            "evidence_ids": list(validated.get("evidence_ids") or []),
        }
        terminal = {
            "type": "escalation",
            "decision_record": _decision_record_from_pending(pending),
            "proposed_action": None,
            "action_validation": gated["action_validation"],
            "escalation": escalation,
        }
    else:
        # Unknown decision: do not consume the token, surface the error.
        _PENDING_APPROVALS[token] = pending
        raise ApprovalError(
            f"decision must be 'approve' or 'reject', got {decision!r}"
        )

    result = _assemble_result(
        plan=plan,
        supervisor_dispatch=pending["supervisor_dispatch"],
        shards=pending["shards"],
        domain_findings=pending["domain_findings"],
        validated=validated,
        terminal=terminal,
        human_decision=decision,
    )
    
    # Attach user comment if provided
    if user_comment:
        result["human_comment"] = user_comment
    
    return result


def _decision_record_from_pending(pending: dict) -> dict:
    """Reconstruct the reducer's decision_record from the paused context.

    The reducer's DecisionRecord is not stored wholesale; it is reproducible
    from the validated situation, but for the resume result we only need the
    stable identity fields the surface reads.  We re-run the reducer so the
    record is authoritative rather than guessed.
    """
    reduction = DecisionReducer().reduce(pending["validated"])
    return reduction["decision_record"]
