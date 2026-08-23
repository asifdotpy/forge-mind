"""ForgeMind Phase 2 — Tier 1 Engineering Supervisor (SPEC-001 T200).

Implements the global coordinator between the Acquire Layer and the
Domain Managers (docs/ARCHITECTURE.md)::

    Event Sources -> Acquire Layer -> TIER 1: Supervisor
                                       -> TIER 2: Domain Managers -> ...

Tier 1 responsibilities performed by :class:`Supervisor`:

1. **Ingestion** — wrap :func:`forgemind.acquisition.acquire_event`
   unchanged (normalize, validate against ``contracts/event.schema.json``,
   derive replay-stable ids, emit the deterministic ``CoveragePlan``).
2. **Traceability** — emit a Supervisor-level trace record,
   ``SupervisorDispatch``, showing the event received, the CoveragePlan
   generated, the managers selected for dispatch, and the dispatch
   decision (why these managers, which global constraints apply).
3. **Constraint enforcement** — enforce the CoveragePlan's
   ``global_constraints`` (``max_concurrent_managers``,
   ``global_timeout_seconds``, ``require_human_above_risk_level``) and
   verify that the managers about to be dispatched match the
   CoveragePlan exactly (no invented, dropped, or rogue managers).

Tier 1 boundaries (violations are architectural bugs):

- Coordinates globally; NEVER performs deep domain AST/log parsing.
- Does NOT make engineering decisions (Tier 5 Reducer).
- Does NOT reconcile cross-domain evidence (Tier 4 Validator).
- Does NOT emit EvidenceShards (Tier 3 Workers) or any other canonical
  artifact — ``SupervisorDispatch`` is a trace record only.
- Does NOT execute managers (Tier 2, Phase 3) or workers (Tier 3,
  Phase 4); dispatch is a recorded decision, not an execution loop.

Determinism contract: no wall-clock values enter any emitted record;
identical inputs produce identical dispatch decisions (replay-stable,
mirroring Phase 1 idempotency).
"""

from __future__ import annotations

from forgemind.acquisition import MANAGERS_BY_DOMAIN, acquire_event

__all__ = ["Supervisor", "SupervisorError"]

#: Allowed values for ``global_constraints.require_human_above_risk_level``.
_ALLOWED_HUMAN_RISK_LEVELS = ("low", "medium", "high", "critical")

#: CoveragePlan keys the Supervisor requires before dispatching.
_REQUIRED_PLAN_KEYS = (
    "coverage_plan_id",
    "situation_id",
    "selected_domains",
    "selected_managers",
    "coverage_requirements",
    "global_constraints",
    "execution_trace_id",
)


class SupervisorError(ValueError):
    """A CoveragePlan failed Supervisor integrity checks or violated a
    global constraint (e.g. more managers than
    ``max_concurrent_managers`` allows)."""


def _validate_positive_int(constraints: dict, key: str) -> int:
    """Require ``constraints[key]`` to be a positive integer (not bool)."""
    value = constraints.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise SupervisorError(
            f"global_constraints.{key} must be a positive integer; "
            f"got {value!r}"
        )
    return value


class Supervisor:
    """Tier 1 global coordinator (docs/ARCHITECTURE.md).

    Stateless and deterministic: call :meth:`process_event` for the full
    ``Event -> CoveragePlan -> SupervisorDispatch`` path, or
    :meth:`dispatch` on an existing CoveragePlan.
    """

    def process_event(self, event, *, execution_trace_id=None) -> dict:
        """Acquire ``event`` and dispatch its CoveragePlan.

        Wraps :func:`forgemind.acquisition.acquire_event` unchanged
        (Phase 1 behavior preserved), then applies Tier 1 dispatch.

        Args:
            event: inbound event dict (canonical Event envelope).
            execution_trace_id: optional explicit trace id forwarded to
                acquisition (must match ``^TRC-[A-Za-z0-9-]+$``).

        Returns:
            dict with keys ``event``, ``coverage_plan`` and
            ``execution_trace_id`` (all from acquisition) plus
            ``supervisor_dispatch`` (the Tier 1 trace record).

        Raises:
            forgemind.acquisition.EventValidationError: invalid event.
            SupervisorError: CoveragePlan failed constraint or
                integrity checks.
        """
        acquired = acquire_event(event, execution_trace_id=execution_trace_id)
        return {
            "event": acquired["event"],
            "coverage_plan": acquired["coverage_plan"],
            "execution_trace_id": acquired["execution_trace_id"],
            "supervisor_dispatch": self.dispatch(acquired["coverage_plan"]),
        }

    def dispatch(self, coverage_plan: dict) -> dict:
        """Validate ``coverage_plan`` and emit the SupervisorDispatch record.

        Enforces the plan's ``global_constraints`` and manager/domain
        consistency, then records the dispatch decision.  No manager is
        executed here — Tier 2 execution belongs to Phase 3.

        Raises:
            SupervisorError: malformed plan, managers not matching the
                plan, or a violated global constraint.
        """
        self._validate_coverage_plan(coverage_plan)
        return _build_dispatch_record(coverage_plan)

    # -- validation --------------------------------------------------------

    @staticmethod
    def _validate_coverage_plan(plan) -> None:
        if not isinstance(plan, dict):
            raise SupervisorError("coverage_plan must be a JSON object")

        missing = [key for key in _REQUIRED_PLAN_KEYS if key not in plan]
        if missing:
            raise SupervisorError(
                f"coverage_plan missing required keys: {missing}"
            )

        constraints = plan["global_constraints"]
        if not isinstance(constraints, dict):
            raise SupervisorError("global_constraints must be a JSON object")
        max_concurrent = _validate_positive_int(
            constraints, "max_concurrent_managers"
        )
        _validate_positive_int(constraints, "global_timeout_seconds")

        risk_level = constraints.get("require_human_above_risk_level")
        if risk_level not in _ALLOWED_HUMAN_RISK_LEVELS:
            raise SupervisorError(
                "global_constraints.require_human_above_risk_level must be "
                f"one of {list(_ALLOWED_HUMAN_RISK_LEVELS)}; got {risk_level!r}"
            )

        if not isinstance(plan["coverage_requirements"], dict):
            raise SupervisorError(
                "coverage_requirements must be a JSON object"
            )

        domains = list(plan["selected_domains"])
        unknown_domains = [d for d in domains if d not in MANAGERS_BY_DOMAIN]
        if unknown_domains:
            raise SupervisorError(
                f"selected_domains contain unknown domains: {unknown_domains}"
            )

        # Dispatched managers must match the CoveragePlan exactly: one
        # canonical manager per selected domain, no additions, no omissions.
        expected_managers = [MANAGERS_BY_DOMAIN[d] for d in domains]
        if list(plan["selected_managers"]) != expected_managers:
            raise SupervisorError(
                "selected_managers do not match CoveragePlan selection "
                f"(expected {expected_managers} for selected_domains "
                f"{domains}); got {plan['selected_managers']!r}"
            )

        if len(expected_managers) > max_concurrent:
            raise SupervisorError(
                "global constraint violated: dispatching "
                f"{len(expected_managers)} managers exceeds "
                f"max_concurrent_managers={max_concurrent}"
            )

        # Coverage sanity: honor declared domain-count bounds when present.
        requirements = plan["coverage_requirements"]
        min_domains = requirements.get("min_domains")
        max_domains = requirements.get("max_domains")
        if isinstance(min_domains, int) and len(domains) < min_domains:
            raise SupervisorError(
                f"coverage requirement violated: {len(domains)} selected "
                f"domains < min_domains={min_domains}"
            )
        if isinstance(max_domains, int) and len(domains) > max_domains:
            raise SupervisorError(
                f"coverage requirement violated: {len(domains)} selected "
                f"domains > max_domains={max_domains}"
            )


# -- trace record -----------------------------------------------------------


def _build_dispatch_record(plan: dict) -> dict:
    domains = list(plan["selected_domains"])
    managers = list(plan["selected_managers"])
    constraints = plan["global_constraints"]
    plan_provenance = plan.get("provenance") or {}
    event_id = plan_provenance.get("event_id")
    if not event_id:
        raise SupervisorError(
            "coverage_plan.provenance.event_id is missing; cannot "
            "establish dispatch provenance (data-model.md Invariant 7)"
        )

    rationale = [
        f"dispatching {len(managers)} manager(s) {managers} for "
        f"selected_domains {domains} per CoveragePlan "
        f"{plan['coverage_plan_id']} (trace {plan['execution_trace_id']})",
        *[
            f"domain {domain!r} -> {MANAGERS_BY_DOMAIN[domain]} "
            "(docs/ARCHITECTURE.md Tier 2 ownership)"
            for domain in domains
        ],
        "coverage decision: excluded_workers retained for visibility of "
        "absence (constitution invariant)",
        "global constraints applied: "
        f"max_concurrent_managers={constraints['max_concurrent_managers']}, "
        f"global_timeout_seconds={constraints['global_timeout_seconds']}, "
        "require_human_above_risk_level="
        f"{constraints['require_human_above_risk_level']!r}",
        "manager execution deferred to Tier 2 Domain Managers "
        "(SPEC-001 Phase 3); the Supervisor performs no specialist "
        "analysis and emits no EvidenceShards",
    ]

    return {
        "artifact_type": "SupervisorDispatch",
        "execution_trace_id": plan["execution_trace_id"],
        "situation_id": plan["situation_id"],
        "coverage_plan_id": plan["coverage_plan_id"],
        "selected_managers": managers,
        "dispatched": True,
        "dispatch_rationale": rationale,
        "coverage_requirements": plan["coverage_requirements"],
        "global_constraints": constraints,
        "provenance": {
            "event_id": event_id,
            "coverage_plan_id": plan["coverage_plan_id"],
            "produced_by": "forgemind.supervisor.Supervisor.dispatch",
            "spec_phase": "SPEC-001-phase-2-tier-1-supervisor",
        },
    }