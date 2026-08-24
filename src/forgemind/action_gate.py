"""ForgeMind Phase 6 — Downstream Action Validation & Safety Gate (SPEC-001 T600).

Implements the pipeline stage AFTER Tier 5 (docs/ARCHITECTURE.md
"Downstream Pipeline — Action Validation & Safety Gate"): every
``ProposedAction`` produced by the Decision Reducer MUST pass this gate
before any execution is recorded, satisfying the spec invariant *"every
proposed action passes the Action Validation boundary"* and the state
machine transition ``action_validation -> resolved | escalated``.

Two public units:

1. :class:`ActionValidationGate` — evaluates a ProposedAction (plus its
   originating DecisionRecord for lineage binding) against the MVP
   policy checks:

   - ``schema-conformance``     — the action is a schema-valid
                                 ``ProposedAction``.
   - ``decision-lineage``       — ``action.decision_id`` references the
                                 paired ``DecisionRecord``; a mismatch is
                                 an integrity error
                                 (:class:`ActionGateError`), not a
                                 policy result.
   - ``blast-radius``           — ``critical`` risk is NEVER allowed
                                 autonomously (``rejected``).
   - ``authorization-boundary`` — actions requiring external authority
                                 (``required_authority`` other than
                                 ``none``) cannot execute autonomously
                                 (``requires_human``).

   The emitted ``ActionValidation.validated_at`` is DERIVED from the
   upstream event timestamp (normalized to UTC ``...Z``), never from
   the wall clock, preserving the repository-wide replay-stability
   convention.

2. :func:`publish_terminal_output` — the SOLE producer of terminal
   outcomes.  Given a gated pair it returns either the executed
   ``Action`` (only reachable with ``policy_result='allowed'``) or an
   ``Escalation`` (``requires_human -> policy_boundary``,
   ``rejected -> validation_failure``).  It refuses forged, stale, or
   missing validations, making a gate bypass structurally impossible.

Determinism: no wall-clock values enter any artifact; identical inputs
yield identical outputs (replay-stable).  All functions are pure and
return fresh records; inputs are never mutated.
"""

from __future__ import annotations

from datetime import datetime, timezone

import jsonschema

from forgemind.acquisition import load_schema

__all__ = [
    "ActionGateError",
    "ActionValidationGate",
    "DEFAULT_REQUIRED_HUMAN_ROLE",
    "publish_terminal_output",
]

#: Canonical human role reused from Tier 5 for gate-side escalations.
DEFAULT_REQUIRED_HUMAN_ROLE = "engineering-on-call"

#: ``required_authority`` values that permit autonomous execution.
_AUTONOMOUS_AUTHORITIES = ("none", "")

#: Allowed ``policy_result`` -> terminal ``ProposedAction.status`` map.
_POLICY_STATUS = {
    "allowed": "validated",
    "requires_human": "proposed",
    "rejected": "rejected",
}


class ActionGateError(ValueError):
    """Downstream Action Validation failure.

    Raised for malformed inputs (non-schema-valid ProposedAction /
    DecisionRecord / ActionValidation), a broken action-to-decision
    lineage, and — critically — ANY attempt to publish a terminal
    outcome without a matching, fresh ActionValidation record (the
    structural no-bypass guard).
    """


def _normalize_timestamp(value) -> str:
    """Normalize an ISO-8601 timestamp to canonical UTC ``...Z`` form.

    Mirrors the acquisition-layer normalization order (parse -> UTC ->
    render) so ``validated_at`` is a pure function of upstream data.
    """
    text = str(value).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise ActionGateError(
            f"event_timestamp must be ISO-8601 parseable; got {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_and_validate(artifact: dict, schema_name: str, label: str) -> None:
    """Validate one artifact against a canonical contract."""
    try:
        jsonschema.validate(artifact, load_schema(schema_name))
    except jsonschema.ValidationError as exc:
        raise ActionGateError(
            f"{label} failed contracts/{schema_name}: {exc.message}"
        ) from exc

class ActionValidationGate:
    """Stateless downstream safety gate: ProposedAction -> ActionValidation."""

    def validate(
        self,
        proposed_action: dict,
        decision_record: dict,
        *,
        event_timestamp,
    ) -> dict:
        """Run the policy checks over one proposed action.

        Args:
            proposed_action: Tier 5 output, schema-valid against
                ``contracts/proposed-action.schema.json``.
            decision_record: the originating DecisionRecord; binds the
                action to its decision lineage.
            event_timestamp: ISO-8601 timestamp from the upstream Event;
                ``validated_at`` is derived deterministically from it.

        Returns:
            ``{"action_validation": ..., "proposed_action": ...}`` where
            the action is an UPDATED COPY with ``status`` mapped from the
            policy result (``allowed -> validated``,
            ``requires_human -> proposed``, ``rejected -> rejected``).

        Raises:
            ActionGateError: invalid inputs or broken decision lineage.
        """
        _load_and_validate(
            proposed_action, "proposed-action.schema.json", "ProposedAction"
        )
        _load_and_validate(
            decision_record, "decision-record.schema.json", "DecisionRecord"
        )
        validated_at = _normalize_timestamp(event_timestamp)

        if (
            proposed_action["decision_id"]
            != decision_record["decision_record_id"]
        ):
            raise ActionGateError(
                f"action {proposed_action['action_id']!r} declares "
                f"decision_id {proposed_action['decision_id']!r} but was "
                "paired with DecisionRecord "
                f"{decision_record['decision_record_id']!r}; refusing to "
                "validate across a broken decision lineage"
            )

        blast_radius_ok = proposed_action["risk_level"] != "critical"
        authority_ok = (
            str(proposed_action.get("required_authority", ""))
            .strip()
            .lower()
            in _AUTONOMOUS_AUTHORITIES
        )

        checks = [
            {
                "check": "schema-conformance",
                "passed": True,
                "detail": (
                    "conforms to contracts/proposed-action.schema.json"
                ),
            },
            {
                "check": "decision-lineage",
                "passed": True,
                "detail": (
                    f"decision_id {proposed_action['decision_id']} matches "
                    "DecisionRecord "
                    f"{decision_record['decision_record_id']}"
                ),
            },
            {
                "check": "blast-radius",
                "passed": blast_radius_ok,
                "detail": (
                    f"risk_level='{proposed_action['risk_level']}'; "
                    "critical risk is never allowed autonomously"
                ),
            },
            {
                "check": "authorization-boundary",
                "passed": authority_ok,
                "detail": (
                    "required_authority='"
                    + str(proposed_action.get("required_authority", ""))
                    + "'; only 'none' executes autonomously"
                ),
            },
        ]

        if not blast_radius_ok:
            policy_result = "rejected"
            reason = (
                "blast radius: risk_level='critical' exceeds the "
                "autonomous execution envelope"
            )
        elif not authority_ok:
            policy_result = "requires_human"
            reason = (
                "authorization boundary: action requires external "
                f"authority '{proposed_action['required_authority']}'"
            )
        else:
            policy_result = "allowed"
            reason = "all policy checks passed"

        updated_action = dict(proposed_action)
        updated_action["status"] = _POLICY_STATUS[policy_result]
        _load_and_validate(
            updated_action,
            "proposed-action.schema.json",
            "Updated ProposedAction",
        )

        action_validation = {
            "validation_id": (
                "AV-"
                + str(proposed_action["action_id"])[len("ACT-"):]
            ),
            "action_id": proposed_action["action_id"],
            "policy_result": policy_result,
            "checks": checks,
            "reason": reason,
            "validated_at": validated_at,
        }
        _load_and_validate(
            action_validation,
            "action-validation.schema.json",
            "ActionValidation",
        )
        return {
            "action_validation": action_validation,
            "proposed_action": updated_action,
        }

def publish_terminal_output(
    proposed_action: dict,
    action_validation: dict,
    *,
    situation_id: str,
    required_human_role: str = DEFAULT_REQUIRED_HUMAN_ROLE,
    evidence_ids=None,
) -> dict:
    """Publish THE terminal outcome for a gated action (no-bypass point).

    This is the only sanctioned way to turn a gated pair into a terminal
    ``Action`` or ``Escalation``.  It refuses to operate without a
    schema-valid ``ActionValidation`` whose ``action_id`` matches the
    proposed action and whose policy result agrees with the action's
    recorded status — forging, replaying, or skipping the gate raises
    :class:`ActionGateError`.

    Args:
        proposed_action: the gated action copy returned by
            :meth:`ActionValidationGate.validate`.
        action_validation: the matching ActionValidation record.
        situation_id: root correlation key (``^SIT-[A-Za-z0-9-]+$``),
            carried into gate-side escalations.
        required_human_role: role recorded on gate-side escalations.
        evidence_ids: optional evidence ids preserved onto escalations.

    Returns:
        ``{"terminal": "action", "action": ..., "escalation": None}``
        for ``allowed`` validations (action marked ``executed``
        in-record — actual side effects stay outside this repository's
        scope), or ``{"terminal": "escalation", "action": ...,
        "escalation": ...}`` (action marked ``escalated``) otherwise.

    Raises:
        ActionGateError: malformed, forged, or stale validation records.
    """
    _load_and_validate(
        proposed_action, "proposed-action.schema.json", "ProposedAction"
    )
    _load_and_validate(
        action_validation, "action-validation.schema.json", "ActionValidation"
    )

    if action_validation["action_id"] != proposed_action["action_id"]:
        raise ActionGateError(
            f"ActionValidation {action_validation['validation_id']!r} "
            f"covers action {action_validation['action_id']!r}, not "
            f"{proposed_action['action_id']!r}; publishing a terminal "
            "outcome WITHOUT a matching validation is a gate bypass and "
            "is refused"
        )

    policy_result = action_validation["policy_result"]
    expected_status = _POLICY_STATUS[policy_result]
    if proposed_action["status"] != expected_status:
        raise ActionGateError(
            "stale or tampered validation: policy_result="
            f"'{policy_result}' requires status '{expected_status}' but "
            f"action carries status '{proposed_action['status']}'"
        )

    suffix = str(situation_id)
    for prefix in ("SIT-", "EVT-"):
        if suffix.startswith(prefix):
            suffix = suffix[len(prefix):]
            break

    if policy_result == "allowed":
        terminal_action = dict(proposed_action)
        terminal_action["status"] = "executed"
        _load_and_validate(
            terminal_action,
            "proposed-action.schema.json",
            "Executed ProposedAction",
        )
        return {
            "terminal": "action",
            "action": terminal_action,
            "escalation": None,
        }

    escalation = {
        "escalation_id": f"ESC-{suffix}",
        "situation_id": situation_id,
        "reason": (
            "validation_failure"
            if policy_result == "rejected"
            else "policy_boundary"
        ),
        "summary": (
            f"gate {action_validation['validation_id']} withheld "
            f"{proposed_action['action_id']} ({policy_result}): "
            f"{action_validation['reason']}"
        ),
        "required_human_role": required_human_role,
        "evidence_ids": list(evidence_ids or []),
    }
    _load_and_validate(
        escalation, "escalation.schema.json", "Gate-side Escalation"
    )
    terminal_action = dict(proposed_action)
    terminal_action["status"] = "escalated"
    _load_and_validate(
        terminal_action,
        "proposed-action.schema.json",
        "Escalated ProposedAction",
    )
    return {
        "terminal": "escalation",
        "action": terminal_action,
        "escalation": escalation,
    }