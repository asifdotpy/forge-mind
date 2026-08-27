"""M3-A judge-visible surface: pure derivation of the M3 proof block.

Presentation-only (SPEC-001 M3-A / T720).  This module contains ZERO tier
logic: it reads the dict returned by :func:`forgemind.api.run_pipeline` and
projects it into the four judge-visible properties:

1. ``provenance_links``     — unbroken Event -> Terminal lineage.
2. ``validation_verdict``   — what the downstream safety gate decided.
3. ``uncertainty_summary``  — what the system does NOT know.
4. ``human_control_state``  — where the human stays in control.

Every value is pulled defensively with ``.get`` so a missing key yields
``None`` (or an empty list) instead of raising: the surface must render even
for a partially-populated pipeline result.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = ["build_m3_proof"]


def _dict(value: Any) -> Dict[str, Any]:
    """Coerce ``value`` to a dict (``None``/non-dict -> ``{}``)."""
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> List[Any]:
    """Coerce ``value`` to a list (``None``/non-list -> ``[]``)."""
    return list(value) if isinstance(value, (list, tuple)) else []


def _ids(items: Any, *keys: str) -> List[Any]:
    """Collect the first present key of ``keys`` from each dict in ``items``."""
    collected: List[Any] = []
    for item in _list(items):
        item = _dict(item)
        for key in keys:
            if item.get(key) is not None:
                collected.append(item[key])
                break
    return collected


def _union(*sequences: Any) -> List[Any]:
    """Order-preserving union of the given sequences (hashable-safe)."""
    merged: List[Any] = []
    for sequence in sequences:
        for item in _list(sequence):
            if item not in merged:
                merged.append(item)
    return merged


def _verdict_state(
    terminal_type: Optional[str], policy_result: Optional[str]
) -> str:
    """Map terminal type + policy_result onto the judge-visible verdict label."""
    if terminal_type == "action" and policy_result == "allowed":
        return "automated"
    if policy_result == "requires_human":
        return "human_review"
    return "escalated"


def _control_state(
    terminal_type: Optional[str], autonomy_class: Optional[str]
) -> str:
    """Map terminal type + autonomy_class onto the human-control label."""
    if terminal_type == "escalation":
        return "escalated"
    if autonomy_class == "safe_autonomous":
        return "automated"
    if autonomy_class == "human_review":
        return "human_review_required"
    if autonomy_class == "escalate":
        return "escalated"
    return "escalated"


def build_m3_proof(pipeline_result: Dict[str, Any]) -> Dict[str, Any]:
    """Derive the four M3 proof blocks from a ``run_pipeline`` result.

    Pure function, no I/O.  Never raises on missing keys.
    """
    result = _dict(pipeline_result)
    artifacts = _dict(result.get("artifacts"))
    terminal = _dict(result.get("terminal"))

    plan = _dict(artifacts.get("coverage_plan"))
    shards = _list(artifacts.get("evidence_shards"))
    findings = _list(artifacts.get("domain_findings"))
    validated = _dict(artifacts.get("validated_situation"))

    # When deposited at the top level of an `adk_runtime` result the decision
    # record and action_validation are stored directly (not inside `terminal`),
    # e.g. for paused workflows. Use those when `terminal` does not carry them.
    result_decision = _dict(result.get("decision_record"))
    result_validation = _dict(result.get("action_validation"))
    decision_record = _dict(terminal.get("decision_record")) or result_decision
    proposed_action = _dict(terminal.get("proposed_action"))
    action_validation = _dict(terminal.get("action_validation")) or result_validation
    escalation = _dict(terminal.get("escalation"))

    terminal_type = terminal.get("type")
    policy_result = action_validation.get("policy_result")
    autonomy_class = decision_record.get("autonomy_class")

    coverage_plan_id = plan.get("coverage_plan_id")
    event_id = _dict(plan.get("provenance")).get("event_id")
    situation_id = result.get("situation_id") or plan.get("situation_id")
    execution_trace_id = result.get("trace_id") or plan.get(
        "execution_trace_id"
    )

    terminal_id = (
        proposed_action.get("action_id")
        if terminal_type == "action"
        else escalation.get("escalation_id")
    )

    artifact_chain = [
        {
            "artifact": "coverage_plan",
            "id": coverage_plan_id,
            "upstream": ["event_id"],
        },
        {
            "artifact": "evidence_shards",
            "id": _ids(shards, "evidence_shard_id") or len(shards),
            "upstream": ["coverage_plan_id"],
        },
        {
            "artifact": "domain_findings",
            "id": _ids(findings, "finding_id"),
            "upstream": ["evidence_shard_ids"],
        },
        {
            "artifact": "validated_situation",
            "id": validated.get("validated_situation_id"),
            "upstream": ["finding_ids", "coverage_plan_id"],
        },
        {
            "artifact": "decision_record",
            "id": decision_record.get("decision_record_id"),
            "upstream": ["validated_situation_id"],
        },
        {
            "artifact": "action_validation",
            "id": action_validation.get("validation_id"),
            "upstream": ["action_id"],
        },
        {
            "artifact": "terminal",
            "id": terminal_id,
            "upstream": ["validation_id"],
        },
    ]

    coverage = _dict(validated.get("coverage"))

    return {
        "provenance_links": {
            "event_id": event_id,
            "coverage_plan_id": coverage_plan_id,
            "execution_trace_id": execution_trace_id,
            "situation_id": situation_id,
            "artifact_chain": artifact_chain,
        },
        "validation_verdict": {
            "state": _verdict_state(terminal_type, policy_result),
            "policy_result": policy_result,
            "reason": action_validation.get("reason")
            or escalation.get("reason"),
            "validation_id": action_validation.get("validation_id"),
        },
        "uncertainty_summary": {
            "causality_status": validated.get("causality_status"),
            "confidence": validated.get("confidence"),
            "missing_domains": _list(coverage.get("missing_domains")),
            "coverage_percentage": coverage.get("coverage_percentage"),
            "uncertainties": _union(
                validated.get("uncertainties"),
                decision_record.get("uncertainties"),
            ),
        },
        "human_control_state": {
            "state": _control_state(terminal_type, autonomy_class),
            "autonomy_class": autonomy_class,
            "required_human_role": escalation.get("required_human_role"),
            "risk_level": decision_record.get("risk_level"),
        },
    }
