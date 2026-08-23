"""ForgeMind Phase 3 — Tier 2 Domain Managers (SPEC-001 T300).

Bounded coordinators between the Tier 1 Supervisor and Tier 3 Specialist
Workers (docs/ARCHITECTURE.md).  Each manager accepts the ``SupervisorDispatch``
that selected it, the corresponding ``CoveragePlan``, and schema-valid
``EvidenceShard``\\s; validates bounded-domain discipline (data-model.md
Invariant 2); aggregates the evidence into a schema-valid ``DomainFinding``;
and emits it.  No final decision is made here (Tier 5) and no cross-domain
reconciliation is performed (Tier 4).

Tier 2 responsibilities implemented:

1. **Bounded domain dispatch** --- one canonical domain per manager
   (``code`` / ``delivery`` / ``production``).
2. **Local retry / timeout handling** --- accepted as configuration and
   surfaced in the ``coverage`` summary; not executed here (worker retries
   are Tier 3 / Phase 4).
3. **Aggregation** --- ``EvidenceShard``\\s fold into one ``DomainFinding``
   per domain, preserving uncertainty and using a conservative confidence
   (minimum across shards; ``0.0`` for empty evidence).

Boundaries (violations are architectural bugs): managers aggregate ONLY within
their bounded domain, make NO decisions, emit NO EvidenceShards, and never
reconcile across domains.

Determinism: no wall-clock values enter any finding; identical inputs yield
identical findings (replay-stable).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Optional

import jsonschema

from forgemind.acquisition import MANAGERS_BY_DOMAIN, load_schema

__all__ = [
    "CodeIntelligenceManager",
    "DeliveryHealthManager",
    "DomainError",
    "DomainManager",
    "DomainManagerError",
    "ManagerCoordinator",
    "ManagerRegistry",
    "ProductionHealthManager",
]

#: Negation prefixes used by the conservative within-domain conflict heuristic.
_NEGATION_PREFIXES = ("never ", "without ", "no ", "not ", "cannot ")


def _negation_pair(claim: str):
    """Return ``(canonical_key, positive_form)`` when ``claim`` negates.

    Only the first verbatim prefix is stripped; anything else is ``(None, None)``.
    """
    lowered = claim.strip().lower()
    for prefix in _NEGATION_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix):], lowered[len(prefix):]
    return None, None


def _ordered_unique(values: Iterable) -> list:
    """Order-preserving dedupe (deterministic for replay)."""
    seen = set()
    kept: list = []
    for value in values:
        if value not in seen:
            seen.add(value)
            kept.append(value)
    return kept


def _detect_conflicts(shards: list) -> list:
    """Flag negation-prefixed claims co-occurring within this domain.

    Documented MVP heuristic: a negated claim is flagged only when its
    positive form was already seen in the same manager's shards.  Intentionally
    conservative --- real reconciliation is Tier 4 (Phase 5).
    """
    conflicts: list = []
    positives: dict = {}
    for shard in shards:
        domain = shard.get("domain")
        for claim in shard.get("claims", []):
            negated_key, positive = _negation_pair(claim)
            if negated_key is None:
                continue
            if negated_key in positives:
                conflicts.append(
                    f"conflicting claim within {domain}: {claim!r}"
                )
            positives.setdefault(negated_key, positive)
    return _ordered_unique(conflicts)


class DomainError(ValueError):
    """Invariant failure in a bounded domain.

    Raised for cross-domain evidence (Invariant 2), malformed / schema-invalid
    coverage plans or evidence shards, a manager operating on coverage it was
    not selected for, or a schema-invalid emitted finding.
    """


# Friendly alias matching the codebase error-naming convention.
DomainManagerError = DomainError


class DomainManager(ABC):
    """Base class for the three Tier 2 bounded domain managers.

    Subclasses pin ``domain`` and inherit the deterministic aggregation
    pipeline.  Managers are stateless with respect to any single finding:
    :meth:`build_finding` returns a fresh record for each call.

    Retry / timeout knobs are configuration surfaced in the coverage summary;
    they are not executed here (worker retries belong to Tier 3, Phase 4).
    """

    def __init__(
        self,
        *,
        retry_attempts: int = 0,
        retry_delay_seconds: float = 0.0,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        if retry_attempts < 0:
            raise DomainError("retry_attempts must be a non-negative integer")
        if retry_delay_seconds < 0:
            raise DomainError("retry_delay_seconds must be non-negative")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise DomainError("timeout_seconds must be a positive number")
        self.retry_attempts = int(retry_attempts)
        self.retry_delay_seconds = float(retry_delay_seconds)
        self.timeout_seconds = (
            float(timeout_seconds) if timeout_seconds is not None else None
        )

    @property
    @abstractmethod
    def domain(self) -> str:
        """The canonical domain this manager owns (abstract)."""

    @property
    def manager_name(self) -> str:
        """Canonical manager name mapped from the owned domain."""
        return MANAGERS_BY_DOMAIN[self.domain]

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(domain={self.domain!r})"

    # -- public aggregation API ------------------------------------------

    def build_finding(
        self,
        supervisor_dispatch: dict,
        coverage_plan: dict,
        evidence_shards: Optional[Iterable[dict]] = None,
    ) -> dict:
        """Aggregate ``evidence_shards`` into a schema-valid DomainFinding.

        Args:
            supervisor_dispatch: the Tier 1 ``SupervisorDispatch`` record that
                selected this manager for ``coverage_plan``.
            coverage_plan: the CoveragePlan this manager was dispatched for.
            evidence_shards: schema-valid EvidenceShards to aggregate; all must
                belong to ``self.domain`` (Invariant 2).  None / empty aggregates
                to a finding with empty arrays, never an error.

        Returns:
            A ``DomainFinding`` dict that validates against
            ``contracts/domain-finding.schema.json``.

        Raises:
            DomainError: manager not selected, dispatch/plan mismatch,
                schema-invalid shard, or cross-domain shard.
        """
        self._assert_dispatch_and_plan(dispatch=supervisor_dispatch, plan=coverage_plan)
        shards = self._validate_bounded_shards(list(evidence_shards or []))
        finding = self._aggregate_shards(
            plan=coverage_plan, dispatch=supervisor_dispatch, shards=shards
        )
        self._validate_finding(finding)
        return finding

    # -- validation guards ------------------------------------------------

    def _assert_dispatch_and_plan(self, *, dispatch: dict, plan: dict) -> None:
        """Ensure this manager was actually selected by ``plan`` / ``dispatch``.

        A manager must never aggregate for coverage it was not dispatched for
        (Invariant 2: bounded-domain dispatch).
        """
        if not isinstance(plan, dict):
            raise DomainError("coverage_plan must be a JSON object")
        if not isinstance(dispatch, dict):
            raise DomainError("supervisor_dispatch must be a JSON object")

        for key in ("execution_trace_id", "situation_id", "coverage_plan_id"):
            if plan.get(key) != dispatch.get(key):
                raise DomainError(
                    f"supervisor_dispatch.{key} does not match coverage_plan "
                    f"({plan.get(key)!r} != {dispatch.get(key)!r})"
                )

        domains = list(plan.get("selected_domains") or [])
        if self.domain not in domains:
            raise DomainError(
                f"{self.manager_name!r} was not selected for coverage "
                f"(selected_domains={domains!r}); a manager aggregates ONLY "
                "within its bounded domain (data-model.md Invariant 2)"
            )

        if self.manager_name not in list(dispatch.get("selected_managers") or []):
            raise DomainError(
                f"{self.manager_name!r} not present in "
                "supervisor_dispatch.selected_managers"
            )

    def _validate_bounded_shards(self, shards: list) -> list:
        """Validate every shard against the EvidenceShard schema and the
        bounded-domain invariant (Invariant 2)."""
        schema = load_schema("evidence-shard.schema.json")
        validated: list = []
        for index, shard in enumerate(shards):
            if not isinstance(shard, dict):
                raise DomainError(f"evidence_shards[{index}] must be a JSON object")
            try:
                jsonschema.validate(shard, schema)
            except jsonschema.ValidationError as exc:
                raise DomainError(
                    f"evidence_shards[{index}] failed "
                    "contracts/evidence-shard.schema.json: "
                    f"{exc.message}"
                ) from exc
            if shard.get("domain") != self.domain:
                raise DomainError(
                    f"{self.manager_name!r} cannot aggregate evidence from "
                    f"domain {shard.get('domain')!r}; managers aggregate ONLY "
                    "within their bounded domain (data-model.md Invariant 2)"
                )
            validated.append(shard)
        return validated
# -- aggregation -------------------------------------------------------

    def _aggregate_shards(
        self, *, plan: dict, dispatch: dict, shards: list
    ) -> dict:
        """Deterministic aggregation of ``shards`` into a DomainFinding dict."""
        event_id = (
            (plan.get("provenance") or {}).get("event_id")
            or (dispatch.get("provenance") or {}).get("event_id")
            or plan.get("coverage_plan_id")
        )
        suffix = self._id_suffix(event_id)
        coverage_plan_id = plan["coverage_plan_id"]
        execution_trace_id = plan["execution_trace_id"]

        shard_ids = _ordered_unique(s["evidence_shard_id"] for s in shards)
        claims = _ordered_unique(
            claim for s in shards for claim in s.get("claims", [])
        )
        uncertainties = _ordered_unique(
            item for s in shards for item in s.get("uncertainties", [])
        )
        conflicts = _detect_conflicts(shards)
        confidence = min(s["confidence"] for s in shards) if shards else 0.0

        if shards:
            summary = (
                f"Aggregated {len(shards)} EvidenceShard(s) for the "
                f"{self.domain} domain ({self.manager_name}); "
                f"{len(claims)} supported claim(s), {len(conflicts)} "
                f"conflict(s), {len(uncertainties)} uncertainty/ies preserved."
            )
        else:
            summary = (
                f"No EvidenceShard provided for the {self.domain} domain; "
                "no supported claims or conflicts recorded."
            )

        return {
            "finding_id": f"FND-{suffix}-{self.domain}",
            "situation_id": plan["situation_id"],
            "domain": self.domain,
            "evidence_shard_ids": shard_ids,
            "summary": summary,
            "supported_claims": claims,
            "conflicts": conflicts,
            "coverage": {
                "domain": self.domain,
                "evidence_shard_count": len(shards),
                "coverage_scope": "all" if shards else "none",
                "retry_attempts": self.retry_attempts,
                "retry_delay_seconds": self.retry_delay_seconds,
                "timeout_seconds": self.timeout_seconds,
            },
            "confidence": float(confidence),
            "uncertainties": uncertainties,
            "provenance": {
                "event_id": event_id,
                "situation_id": plan["situation_id"],
                "coverage_plan_id": coverage_plan_id,
                "execution_trace_id": execution_trace_id,
                "evidence_shard_ids": shard_ids,
                "produced_by": type(self).__name__,
                "spec_phase": "SPEC-001-phase-3-tier-2-domain-managers",
            },
            "execution_trace_id": execution_trace_id,
        }

    @staticmethod
    def _id_suffix(event_id: str) -> str:
        """Replay-stable suffix for generated ids (mirrors acquisition)."""
        for prefix in ("EVT-", "CP-"):
            if event_id.startswith(prefix):
                return event_id[len(prefix):]
        return str(event_id or "unknown")

    def _validate_finding(self, finding: dict) -> None:
        """Re-validate the emitted finding against its canonical schema."""
        try:
            jsonschema.validate(finding, load_schema("domain-finding.schema.json"))
        except jsonschema.ValidationError as exc:  # pragma: no cover
            raise DomainError(
                "generated DomainFinding failed "
                "contracts/domain-finding.schema.json: "
                f"{exc.message}"
            ) from exc
class CodeIntelligenceManager(DomainManager):
    """Owns the code domain: PR changesets, AST impact, doc drift, spec conformance."""

    @property
    def domain(self) -> str:
        return "code"


class DeliveryHealthManager(DomainManager):
    """Owns the delivery domain: CI/CD builds, flakiness, deployment gates, alerts."""

    @property
    def domain(self) -> str:
        return "delivery"


class ProductionHealthManager(DomainManager):
    """Owns production: telemetry, anomaly correlation, vulnerability scans."""

    @property
    def domain(self) -> str:
        return "production"


class ManagerRegistry:
    """Factory mapping a canonical domain to its concrete manager class.

    Instances are stateless builders for :class:`ManagerCoordinator`.
    """

    managers_by_domain = {
        "code": CodeIntelligenceManager,
        "delivery": DeliveryHealthManager,
        "production": ProductionHealthManager,
    }

    def __init__(self, **manager_kwargs) -> None:
        self._instances = {
            domain: cls(**manager_kwargs)
            for domain, cls in self.managers_by_domain.items()
        }

    def get(self, domain: str) -> DomainManager:
        if domain not in self._instances:
            raise DomainError(
                f"unknown domain {domain!r}; known domains: {sorted(self._instances)}"
            )
        return self._instances[domain]

    def domains(self) -> tuple:
        return tuple(self._instances)


class ManagerCoordinator:
    """Run the CoveragePlan-selected managers independently and (when coverage
    permits) concurrently, bounded by ``max_concurrent_managers``.

    Evidence is grouped by domain; any shard whose domain was not selected for
    coverage is rejected before any manager runs (Invariant 2).  Each selected
    domain that received evidence is aggregated by its manager.
    """

    def __init__(self, registry: Optional[ManagerRegistry] = None) -> None:
        self._registry = registry or ManagerRegistry()

    def dispatch(
        self,
        supervisor_dispatch: dict,
        coverage_plan: dict,
        evidence_shards: Optional[Iterable[dict]] = None,
        *,
        max_concurrent_managers: Optional[int] = None,
    ) -> dict:
        """Produce a mapping of domain -> DomainFinding for the plan.

        Returns ``{"findings": {domain: finding}, "rejected": [...],
        "errors": {domain: message}}``.
        """
        if not isinstance(coverage_plan, dict):
            raise DomainError("coverage_plan must be a JSON object")
        selected_domains = [
            d
            for d in coverage_plan.get("selected_domains") or []
            if d in MANAGERS_BY_DOMAIN
        ]

        shards = list(evidence_shards or [])
        grouped: dict = {}
        for shard in shards:
            grouped.setdefault(shard.get("domain"), []).append(shard)

        rejected: list = []
        for domain in list(grouped):
            if domain not in selected_domains:
                rejected.append(
                    f"evidence for unselected domain {domain!r} rejected "
                    "(Invariant 2: bounded-domain aggregation)"
                )
                del grouped[domain]

        # Per-domain managers run independently over *their own* shards.
        workers = [d for d in selected_domains if d in grouped]
        pool_size = max_concurrent_managers or coverage_plan.get(
            "global_constraints", {}
        ).get("max_concurrent_managers") or 1
        pool_size = max(1, int(pool_size))

        findings: dict[str, dict] = {}
        errors: dict[str, str] = {}
        if not workers:
            pass
        elif len(workers) == 1:
            domain = workers[0]
            try:
                findings[domain] = self._registry.get(domain).build_finding(
                    supervisor_dispatch, coverage_plan, grouped[domain]
                )
            except Exception as exc:  # surface genuine per-manager failures
                errors[domain] = str(exc)
        else:
            with ThreadPoolExecutor(max_workers=pool_size) as pool:
                future_map = {
                    pool.submit(
                        self._registry.get(d).build_finding,
                        supervisor_dispatch,
                        coverage_plan,
                        grouped[d],
                    ): d
                    for d in workers
                }
                for future in as_completed(future_map):
                    domain = future_map[future]
                    try:
                        findings[domain] = future.result()
                    except Exception as exc:  # surface per-manager failures
                        errors[domain] = str(exc)

        return {
            "findings": findings,
            "rejected": rejected,
            "errors": errors,
        }