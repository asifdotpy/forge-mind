"""ForgeMind Phase 6 — Tier 5 Decision Reducer & Publisher (SPEC-001 T600).

The sole tier authorized to convert a ``ValidatedSituation`` into an
operational decision (docs/ARCHITECTURE.md Tier 5, ADR-006).  The reducer
consumes *only* validated situations — never raw ``EvidenceShard``\\s,
``DomainFinding``\\s, or ``CoveragePlan``\\s — and evaluates each against
the enterprise autonomy/risk policy implemented as a deterministic
threshold ladder:

- ``escalate``        — confidence below ``ESCALATE_CONFIDENCE`` (0.5),
                        coverage gaps, or unresolved cross-domain
                        conflicts.  No action is proposed; an
                        ``Escalation`` artifact is emitted instead
                        (state machine: ``decision_ready -> escalated``
                        / ``closed_inconclusive``).
- ``human_review``    — confidence below ``AUTONOMOUS_CONFIDENCE``
                        (0.75), or causality ``unsupported``.  A
                        ``ProposedAction`` IS emitted but flagged
                        ``requires_human=True``.
- ``safe_autonomous`` — confidence >= 0.75 AND causality ``correlated``,
                        ``supported`` or ``verified`` (ADR-011: presence-
                        based multi-domain corroboration counts as
                        established) AND zero conflicting evidence AND
                        full coverage.  The action may proceed
                        autonomously.

Escalation ``reason`` precedence is deterministic: ``coverage_gap`` wins
over ``uncertainty``; ``risk`` / ``policy_boundary`` /
``validation_failure`` belong to the downstream gate
(``forgemind.action_gate``).

Boundaries (violations are architectural bugs): the reducer proposes,
publishes, and escalates — it NEVER executes anything.  Every emitted
artifact is re-validated against its canonical JSON Schema contract
before return; ``autonomy_class='safe_autonomous'`` still yields a
merely *proposed* action whose execution authority lives exclusively in
the downstream Action Validation gate.

Determinism: identifiers are pure functions of ``situation_id``
(``DR-<suffix>`` / ``ACT-<suffix>`` / ``ESC-<suffix>``); no wall-clock
values enter any artifact, so identical inputs yield byte-identical
outputs (replay-stable).  The reducer is stateless — :meth:`reduce`
returns freshly constructed records and never mutates its input.
"""

from __future__ import annotations

import jsonschema

from forgemind.acquisition import load_schema

__all__ = [
    "AUTONOMOUS_CONFIDENCE",
    "DEFAULT_REQUIRED_HUMAN_ROLE",
    "ESCALATE_CONFIDENCE",
    "DecisionReducer",
    "ReducerError",
]

#: Confidence at/above which a fully-corroborated situation may proceed
#: autonomously (policy ladder, approved 2026-08-24 review).
AUTONOMOUS_CONFIDENCE = 0.75

#: Confidence below which a situation always escalates (policy ladder).
ESCALATE_CONFIDENCE = 0.5

#: Canonical human role for escalations and externally-gated actions.
DEFAULT_REQUIRED_HUMAN_ROLE = "engineering-on-call"

#: Causality statuses counted as *established* for autonomous operation.
_ESTABLISHED_CAUSALITY = ("supported", "verified", "correlated")

#: Canonical Escalation reason labels (contracts/escalation.schema.json).
_ESCALATION_REASONS = (
    "uncertainty",
    "risk",
    "coverage_gap",
    "policy_boundary",
    "validation_failure",
)

#: Risk-adaptive confidence strategy (Fix 4).
#: Different risk levels use different confidence aggregation strategies:
#: - low: evidence-weighted (average with evidence strength bonus)
#: - medium: conservative weighted (min of average and evidence-weighted)
#: - high: weakest-link (min confidence across findings)
#: - critical: human approval required (no autonomous action)
RISK_CONFIDENCE_STRATEGY = {
    "low": "evidence_weighted",
    "medium": "conservative_weighted",
    "high": "weakest_link",
    "critical": "human_required",
}

#: Action-risk-dependent evidence threshold (Fix 3).
#: Maps proposed action types to required evidence domains.
#: Each action type requires evidence from specific domains to proceed.
ACTION_REQUIRED_DOMAINS = {
    "post_comment": ["code", "delivery"],
    "auto_merge": ["code", "delivery", "production"],
    "production_remediation": ["code", "delivery", "production"],
    "status_check": ["code", "delivery"],
    "analysis_comment": ["code"],
}

#: Minimum evidence strength required per risk level (Fix 3).
RISK_EVIDENCE_THRESHOLD = {
    "low": 0.33,
    "medium": 0.5,
    "high": 0.67,
    "critical": 1.0,
}


class ReducerError(ValueError):
    """Tier 5 decision-policy failure.

    Raised for an input that is not a schema-valid ``ValidatedSituation``
    (the reducer consumes ONLY validated situations — raw shards,
    findings, or plans are rejected), an escalation requested under an
    unknown reason label, or an emitted DecisionRecord / ProposedAction /
    Escalation failing re-validation against its canonical contract.
    """


def _id_suffix(artifact_id: str) -> str:
    """Replay-stable suffix for generated ids (mirrors earlier tiers)."""
    for prefix in ("VS-", "SIT-", "EVT-", "DR-", "ACT-", "ESC-", "CP-"):
        if artifact_id.startswith(prefix):
            return artifact_id[len(prefix):]
    return str(artifact_id or "unknown")


def _validate_situation(validated_situation) -> dict:
    """Accept ONLY a schema-valid ValidatedSituation (ADR-006 input rule)."""
    if not isinstance(validated_situation, dict):
        raise ReducerError(
            "DecisionReducer consumes only ValidatedSituation objects; "
            f"got {type(validated_situation).__name__}"
        )
    try:
        jsonschema.validate(
            validated_situation, load_schema("validated-situation.schema.json")
        )
    except jsonschema.ValidationError as exc:
        raise ReducerError(
            "input is not a schema-valid ValidatedSituation "
            "(contracts/validated-situation.schema.json): "
            f"{exc.message}.  The reducer never accepts raw shards, "
            "findings, or plans — run the Tier 4 validator first."
        ) from exc
    return validated_situation

class DecisionReducer:
    """Stateless Tier 5 policy evaluator: ValidatedSituation -> decision.

    One instance may be reused for any number of reductions; every
    :meth:`reduce` call returns freshly constructed records and never
    mutates its inputs.
    """

    def reduce(self, validated_situation: dict) -> dict:
        """Reduce one ValidatedSituation to its operational decision.

        Args:
            validated_situation: the Tier 4 output, schema-valid against
                ``contracts/validated-situation.schema.json``.

        Returns:
            ``{"decision_record": ..., "proposed_action": ...|None,
            "escalation": ...|None}`` where EXACTLY ONE of
            ``proposed_action`` / ``escalation`` is present:

            - ``safe_autonomous`` / ``human_review`` decisions carry a
              ``ProposedAction`` with ``status="proposed"`` (never
              ``executed`` — execution authority belongs to the gate);
            - ``escalate`` decisions carry an ``Escalation`` and NO
              proposed action.

        Raises:
            ReducerError: invalid input, or an emitted artifact failing
                schema re-validation.
        """
        situation = _validate_situation(validated_situation)

        confidence_raw = float(situation["confidence"])
        causality_status = situation["causality_status"]
        conflicts = list(situation.get("conflicting_evidence") or [])
        coverage = situation.get("coverage") or {}
        missing_domains = list(coverage.get("missing_domains") or [])
        provided_count = len(coverage.get("provided_domains") or [])

        # -- evidence-aware fields from validator (Fix 2, 3, 4) --------------
        evidence_strength = float(situation.get("evidence_strength", 0.0))
        evidence_states = situation.get("evidence_states", {}) or {}
        cross_worker_consistency = (
            situation.get("cross_worker_consistency", {}) or {}
        )
        claim_statuses = situation.get("claim_statuses", {}) or {}

        # -- base confidence boost (preserves old behavior) ----------------
        # Reward well-evidenced situations: full coverage + established causality
        if not missing_domains and causality_status in _ESTABLISHED_CAUSALITY:
            base_confidence = confidence_raw + 0.05
        else:
            base_confidence = confidence_raw

        # -- deterministic risk classification (Fix 4) ----------------------
        # Use base confidence for initial risk assessment
        if conflicts or base_confidence < ESCALATE_CONFIDENCE:
            risk_level = "high"
        elif (
            base_confidence < AUTONOMOUS_CONFIDENCE
            or causality_status not in _ESTABLISHED_CAUSALITY
        ):
            risk_level = "medium"
        else:
            risk_level = "low"

        # Check for high/critical credible findings (Fix 5)
        has_high_critical_evidence = self._has_high_critical_evidence(
            evidence_states, claim_statuses
        )
        if has_high_critical_evidence and risk_level in ("low", "medium"):
            risk_level = "high"

        # -- risk-adaptive confidence strategy (Fix 4) ----------------------
        confidence = self._apply_confidence_strategy(
            confidence_raw=confidence_raw,
            evidence_strength=evidence_strength,
            risk_level=risk_level,
            causality_status=causality_status,
            missing_domains=missing_domains,
        )

        # -- action-risk-dependent evidence threshold (Fix 3) ---------------
        # Check if evidence is adequate for the proposed action
        evidence_adequate = self._check_evidence_adequacy(
            evidence_strength=evidence_strength,
            risk_level=risk_level,
            provided_domains=coverage.get("provided_domains", []),
            missing_domains=missing_domains,
        )

        # -- deterministic policy ladder -----------------------------------
        escalate_triggers = []
        if confidence < ESCALATE_CONFIDENCE:
            escalate_triggers.append(
                f"confidence {confidence} below escalate threshold "
                f"{ESCALATE_CONFIDENCE}"
            )
        if missing_domains:
            escalate_triggers.append(
                "coverage gap: no findings for selected domain(s) "
                f"{missing_domains}"
            )
        if conflicts:
            escalate_triggers.append(
                f"{len(conflicts)} unresolved cross-domain conflict(s)"
            )

        # Cross-worker contradictions trigger escalation
        if cross_worker_consistency.get("contradictions"):
            escalate_triggers.append(
                "cross-worker contradictions: "
                + "; ".join(cross_worker_consistency["contradictions"])
            )

        if escalate_triggers:
            autonomy_class = "escalate"
            reason = "coverage_gap" if missing_domains else "uncertainty"
        elif (
            confidence < AUTONOMOUS_CONFIDENCE
            or causality_status not in _ESTABLISHED_CAUSALITY
        ):
            autonomy_class = "human_review"
            reason = None
        elif not evidence_adequate:
            # Evidence strength insufficient for proposed action (Fix 3)
            autonomy_class = "human_review"
            reason = None
        elif has_high_critical_evidence:
            # High/critical credible findings cannot be averaged away (Fix 5)
            autonomy_class = "escalate"
            reason = "risk"
        else:
            autonomy_class = "safe_autonomous"
            reason = None

        requires_human = autonomy_class != "safe_autonomous"

        suffix = _id_suffix(situation["situation_id"])
        record = {
            "decision_record_id": f"DR-{suffix}",
            "validated_situation_id": situation["validated_situation_id"],
            "decision": self._decision_text(
                autonomy_class, situation, escalate_triggers
            ),
            "rationale": self._rationale(
                autonomy_class,
                confidence,
                causality_status,
                provided_count,
                len(missing_domains),
                len(conflicts),
                escalate_triggers,
            ),
            "risk_level": risk_level,
            "autonomy_class": autonomy_class,
            "confidence": confidence_raw,
            "uncertainties": list(situation.get("uncertainties") or []),
            "requires_human": requires_human,
        }

        proposed_action = None
        escalation = None
        if autonomy_class == "escalate":
            escalation = self._build_escalation(situation, reason)
        else:
            proposed_action = {
                "action_id": f"ACT-{suffix}",
                "decision_id": record["decision_record_id"],
                "action": (
                    f"execute remediation for: {self._headline(situation)}"
                ),
                "risk_level": risk_level,
                "required_authority": (
                    DEFAULT_REQUIRED_HUMAN_ROLE
                    if requires_human
                    else "none"
                ),
                "status": "proposed",
            }

        # Exactly-one-terminal invariant.
        if (proposed_action is None) == (escalation is None):
            raise ReducerError(  # pragma: no cover - construction cannot hit
                "internal invariant violated: a reduction must produce "
                "exactly one of ProposedAction / Escalation"
            )

        # Boundary guard: the reducer proposes; it never marks execution.
        if (
            proposed_action is not None
            and proposed_action["status"] != "proposed"
        ):
            raise ReducerError(  # pragma: no cover - construction cannot hit
                "Tier 5 proposed an action with non-proposed status; "
                "execution authority belongs to the Action Validation gate"
            )

        for artifact, schema_name in (
            (record, "decision-record.schema.json"),
            (proposed_action, "proposed-action.schema.json"),
            (escalation, "escalation.schema.json"),
        ):
            if artifact is None:
                continue
            try:
                jsonschema.validate(artifact, load_schema(schema_name))
            except jsonschema.ValidationError as exc:  # pragma: no cover
                raise ReducerError(
                    f"generated artifact failed contracts/{schema_name}: "
                    f"{exc.message}"
                ) from exc

        return {
            "decision_record": record,
            "proposed_action": proposed_action,
            "escalation": escalation,
        }

    def escalate(
        self, validated_situation: dict, *, reason: str = None
    ) -> dict:
        """Publish an Escalation for a situation without proposing actions.

        Args:
            validated_situation: schema-valid ValidatedSituation.
            reason: optional explicit ``Escalation.reason`` label; omitted
                resolves deterministically (``coverage_gap`` when the
                situation carries coverage gaps, else ``uncertainty``).

        Returns:
            An ``Escalation`` dict validating against
            ``contracts/escalation.schema.json``.

        Raises:
            ReducerError: invalid input or unknown reason label.
        """
        situation = _validate_situation(validated_situation)
        if reason is None:
            reason = self._default_escalation_reason(situation)
        elif reason not in _ESCALATION_REASONS:
            raise ReducerError(
                f"unknown escalation reason {reason!r}; must be one of "
                + "|".join(_ESCALATION_REASONS)
            )
        escalation = self._build_escalation(situation, reason)
        try:
            jsonschema.validate(
                escalation, load_schema("escalation.schema.json")
            )
        except jsonschema.ValidationError as exc:  # pragma: no cover
            raise ReducerError(
                "generated Escalation failed "
                f"contracts/escalation.schema.json: {exc.message}"
            ) from exc
        return escalation

    # -- construction helpers ---------------------------------------------------

    @staticmethod
    def _default_escalation_reason(situation: dict) -> str:
        """Deterministic reason: coverage_gap wins over uncertainty."""
        coverage = situation.get("coverage") or {}
        if coverage.get("missing_domains"):
            return "coverage_gap"
        return "uncertainty"

    @staticmethod
    def _headline(situation: dict) -> str:
        """Deterministic one-line headline for decisions/actions."""
        supporting = situation.get("supporting_evidence") or []
        if supporting:
            return supporting[0]
        correlations = situation.get("correlations") or []
        if correlations:
            return correlations[0]
        return "situation reconciled without corroborated claims"

    @staticmethod
    def _decision_text(
        autonomy_class: str, situation: dict, escalate_triggers: list
    ) -> str:
        headline = DecisionReducer._headline(situation)
        if autonomy_class == "safe_autonomous":
            return f"Proceed autonomously: {headline}"
        if autonomy_class == "human_review":
            return f"Hold for human review before acting: {headline}"
        return (
            "Escalate; no autonomous action authorized ("
            + "; ".join(escalate_triggers)
            + f"): {headline}"
        )

    @staticmethod
    def _rationale(
        autonomy_class: str,
        confidence: float,
        causality_status: str,
        provided_count: int,
        missing_count: int,
        conflict_count: int,
        escalate_triggers: list,
    ) -> list:
        established = causality_status in _ESTABLISHED_CAUSALITY
        lines = [
            (
                f"autonomy_class='{autonomy_class}' per policy ladder: "
                f"escalate below {ESCALATE_CONFIDENCE}, autonomous at/above "
                f"{AUTONOMOUS_CONFIDENCE} with established causality"
            ),
            (
                f"confidence={confidence}; causality_status="
                f"'{causality_status}' "
                + (
                    "(causation established)"
                    if established
                    else "(correlation, not established causation)"
                )
            ),
            (
                f"coverage: {provided_count} contributing domain(s), "
                f"{missing_count} missing"
            ),
            f"conflicting evidence entries: {conflict_count}",
        ]
        if escalate_triggers:
            lines.append(
                "escalation triggers: " + "; ".join(escalate_triggers)
            )
        return lines

    def _build_escalation(self, situation: dict, reason: str) -> dict:
        suffix = _id_suffix(situation["situation_id"])
        gap_note = ""
        if reason == "coverage_gap":
            coverage = situation.get("coverage") or {}
            gap_note = (
                f" Coverage gaps for {coverage.get('missing_domains') or []};"
            )
        return {
            "escalation_id": f"ESC-{suffix}",
            "situation_id": situation["situation_id"],
            "reason": reason,
            "summary": (
                f"Tier 5 escalated situation {situation['situation_id']} "
                f"(confidence {situation['confidence']}, causality "
                f"'{situation['causality_status']}').{gap_note} No "
                "autonomous action was proposed; human decision required."
            ),
            "required_human_role": DEFAULT_REQUIRED_HUMAN_ROLE,
            "evidence_ids": list(situation.get("evidence_ids") or []),
        }

    # -- evidence-aware decisioning helpers (Fix 3, 4, 5) -----------------------

    @staticmethod
    def _has_high_critical_evidence(
        evidence_states: dict, claim_statuses: dict
    ) -> bool:
        """Check if there is high/critical risk evidence with supporting credibility.

        Fix 5: High/critical credible findings cannot be averaged away.
        A finding is credible if it has SUPPORTED or INDEPENDENTLY_VERIFIED claims.
        """
        # Check for contradictory evidence (always escalates)
        counts = evidence_states.get("counts", {}) if evidence_states else {}
        if counts.get("contradictory", 0) > 0:
            return True

        # Check if any claims are independently verified with high-risk signals
        verified_claims = [
            claim
            for claim, status in claim_statuses.items()
            if status
            in ("supported", "independently_verified", "verified")
        ]
        # If we have verified claims AND evidence strength is meaningful,
        # the finding is credible
        if verified_claims and counts.get("observed", 0) > 0:
            # Check for high-risk keywords in verified claims
            high_risk_keywords = (
                "vulnerability",
                "injection",
                "auth bypass",
                "xss",
                "csrf",
                "rce",
                "privilege escalation",
                "hardcoded",
                "secret",
                "token leakage",
                "critical",
            )
            for claim in verified_claims:
                lowered = claim.lower()
                if any(kw in lowered for kw in high_risk_keywords):
                    return True
        return False

    @staticmethod
    def _apply_confidence_strategy(
        confidence_raw: float,
        evidence_strength: float,
        risk_level: str,
        causality_status: str,
        missing_domains: list,
    ) -> float:
        """Apply risk-adaptive confidence strategy (Fix 4).

        | Risk Level | Confidence Strategy     |
        |------------|-------------------------|
        | Low        | Evidence-weighted       |
        | Medium     | Conservative weighted   |
        | High       | Weakest-link (min)      |
        | Critical   | Human approval required |
        """
        strategy = RISK_CONFIDENCE_STRATEGY.get(
            risk_level, "evidence_weighted"
        )

        if strategy == "human_required":
            # Critical: force below autonomous threshold
            return min(confidence_raw, AUTONOMOUS_CONFIDENCE - 0.01)

        # Base boost for well-evidenced situations
        if not missing_domains and causality_status in _ESTABLISHED_CAUSALITY:
            boosted = confidence_raw + 0.05
        else:
            boosted = confidence_raw

        if strategy == "evidence_weighted":
            # Evidence-weighted: reward high evidence strength
            # Scale: confidence * (0.85 + 0.15 * evidence_strength)
            return round(
                min(1.0, boosted * (0.85 + 0.15 * evidence_strength)), 2
            )

        if strategy == "conservative_weighted":
            # Conservative weighted: min of boosted and evidence-weighted
            evidence_weighted = min(
                1.0, boosted * (0.85 + 0.15 * evidence_strength)
            )
            return round(min(boosted, evidence_weighted), 2)

        if strategy == "weakest_link":
            # Weakest-link: use the minimum of raw confidence and evidence
            # strength (high risk situations require strong evidence)
            return round(min(confidence_raw, evidence_strength), 2)

        return round(boosted, 2)

    @staticmethod
    def _check_evidence_adequacy(
        evidence_strength: float,
        risk_level: str,
        provided_domains: list,
        missing_domains: list,
    ) -> bool:
        """Check if evidence is adequate for the proposed action (Fix 3).

        Autonomy requires BOTH:
        - confidence_score >= threshold
        - evidence_strength >= threshold

        Different risk levels have different evidence thresholds.
        """
        # Missing domains always means inadequate evidence
        if missing_domains:
            return False

        # Get minimum evidence strength threshold for this risk level
        threshold = RISK_EVIDENCE_THRESHOLD.get(risk_level, 0.33)

        return evidence_strength >= threshold