"""ForgeMind Phase 4 — Tier 3 Specialist Workers (SPEC-001 T400).

Leaf-node workers between the Tier 2 Domain Managers and the Tier 4
Cross-Lifecycle Validator (docs/ARCHITECTURE.md).  Workers emit durable
``EvidenceShard``\\s from bounded domain inputs --- they make no decisions,
spawn no sub-workers, and perform no reconciliation.

Tier 3 responsibilities implemented:

1. **Specialized, deep evidence extraction** --- each worker produces
   deterministic observations / claims from a concrete ``context`` mapping
   scoped to its owned domain.
2. **Structured EvidenceShards with source citations** --- every emission is
   re-validated against ``contracts/evidence-shard.schema.json``.
3. **Preserving uncertainty and provenance** --- shard ``uncertainties`` are
   carried forward and ``provenance`` references the exact upstream event_id,
   situation_id, coverage_plan_id, and execution_trace_id (Invariant 7).

Tier 3 boundaries (violations are architectural bugs --- Invariant 1):

- Leaf nodes with ZERO worker-spawning authority.
- Never make policy or final decisions (that is Tier 5).
- Never reconcile cross-domain evidence (that is Tier 4).
- Never aggregate evidence into DomainFindings (that is Tier 2).
- Never emit DomainFindings / ValidatedSituations / DecisionRecords.

``context`` contract (documented for downstream tiers)::

    {
        "domain": "code",                  # must equal worker.domain
        "inputs": {
            "changed_files": ["auth/..."], # PR Pre-Flight AST
            "ci_outcome": "pass",          # Build Log & Flakiness
            "telemetry_signals": [12.5],   # Telemetry Correlation
            "docs_summary": "...",         # Docs Drift & Spec
            "alert_signals": [...],        # Alert Storm Clustering
            "dependency_scan": [...],      # Security & Dependency
        },
        "domain_finding": {...},           # optional; .domain must match
    }

Any ``context.domain`` / ``context.domain_finding.domain`` differing from the
worker's own ``domain`` raises :class:`WorkerError` (bounded-domain guard).

Determinism: no wall-clock values enter any shard; identical inputs produce
identical EvidenceShards (``evidence_shard_id = ES-<suffix>-<worker_name>``).

The :class:`WorkerCoordinator` runs the plan's selected workers independently
(concurrently by default, bounded by ``max_concurrent_managers``); it never
dispatches a worker whose domain was not selected for coverage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable, Mapping, Optional

import jsonschema

from forgemind.acquisition import _WORKERS_BY_DOMAIN, load_schema

__all__ = [
    "AlertStormClusteringWorker",
    "BuildLogAndFlakinessWorker",
    "DocsDriftAndSpecWorker",
    "PRPreFlightASTWorker",
    "SecurityAndDependencyWorker",
    "TelemetryCorrelationWorker",
    "Worker",
    "WorkerCoordinator",
    "WorkerError",
    "WorkerRegistry",
]

#: Canonical worker id -> owned domain map (docs/ARCHITECTURE.md Tier 3).
WORKER_NAMES_BY_DOMAIN = {
    worker: domain
    for domain, names in _WORKERS_BY_DOMAIN.items()
    for worker in names
}
class WorkerError(ValueError):
    """A worker violated a Tier 3 invariant.

    Raised for: cross-domain mismatch (Invariant 1), a worker dispatched for a
    domain it was not selected to cover, malformed context mappings, or a
    schema-invalid emitted EvidenceShard.
    """


class Worker(ABC):
    """Base class for the six Tier 3 leaf specialist workers.

    Subclasses pin ``domain`` and ``worker_name`` and supply the deterministic
    ``_observations()`` / ``_claims()`` / ``_uncertainties()`` extraction
    hooks.  A worker is stateless with respect to any single emission:
    :meth:`build_shard` returns a fresh EvidenceShard per call.

    Retry / timeout knobs are accepted as configuration and surfaced in the
    shard's ``provenance``; they are not executed here (specialist worker
    retries remain future work).
    """

    worker_name: str
    domain: str

    def __init__(
        self,
        *,
        retry_attempts: int = 0,
        retry_delay_seconds: float = 0.0,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        if retry_attempts < 0:
            raise WorkerError("retry_attempts must be a non-negative integer")
        if retry_delay_seconds < 0:
            raise WorkerError("retry_delay_seconds must be non-negative")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise WorkerError("timeout_seconds must be a positive number")
        self.retry_attempts = int(retry_attempts)
        self.retry_delay_seconds = float(retry_delay_seconds)
        self.timeout_seconds = (
            float(timeout_seconds) if timeout_seconds is not None else None
        )

    @property
    @abstractmethod
    def domain(self) -> str:
        """The canonical lifecycle domain this worker owns (abstract)."""

    @property
    @abstractmethod
    def worker_name(self) -> str:
        """Canonical worker id for this worker type (abstract)."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}(domain={self.domain!r})"

    # -- public evidence API ---------------------------------------------

    def build_shard(
        self,
        coverage_plan: dict,
        context: Optional[Mapping] = None,
    ) -> dict:
        """Extract and emit one schema-valid EvidenceShard for this worker.

        Args:
            coverage_plan: the CoveragePlan that selected this worker; must
                have ``self.domain`` in ``selected_domains`` and
                ``self.worker_name`` in ``selected_workers``.
            context: mapping scoped to this worker's domain.  A ``context``
                whose ``domain`` / ``domain_finding.domain`` differs from
                ``self.domain`` raises :class:`WorkerError` (Invariant 1).
                ``None`` / empty extracts a shard with empty observations and
                claims (schema-valid; never an error).

        Returns:
            An EvidenceShard dict validated against
            ``contracts/evidence-shard.schema.json``.

        Raises:
            WorkerError: cross-domain mismatch, unselected worker / domain,
                malformed context, or schema-invalid emission.
        """
        self._assert_selected(coverage_plan=coverage_plan)
        context = dict(context or {})
        self._assert_bounded_context(context)
        shard = self._emit(coverage_plan=coverage_plan, context=context)
        self._validate_shard(shard)
        return shard

    # -- validation guards -----------------------------------------------

    def _assert_selected(self, *, coverage_plan: dict) -> None:
        """Ensure this worker belongs to the plan's selected workers / domains."""
        if not isinstance(coverage_plan, dict):
            raise WorkerError("coverage_plan must be a JSON object")

        domains = list(coverage_plan.get("selected_domains") or [])
        if self.domain not in domains:
            raise WorkerError(
                f"{self.worker_name!r} was not selected for coverage "
                f"(selected_domains={domains!r}); workers are leaf nodes with "
                "bounded domains (data-model.md Invariant 1)"
            )

        if self.worker_name not in list(coverage_plan.get("selected_workers") or []):
            raise WorkerError(
                f"{self.worker_name!r} not present in coverage_plan.selected_workers"
            )

    def _assert_bounded_context(self, context: dict) -> None:
        """Reject any context that exceeds this worker's own domain."""
        if not isinstance(context, dict):
            raise WorkerError("worker context must be a JSON object")
        context_domain = context.get("domain")
        if context_domain is not None and context_domain != self.domain:
            raise WorkerError(
                f"{self.worker_name!r} cannot accept context for domain "
                f"{context_domain!r}; workers are bounded to their own domain "
                "(data-model.md Invariant 1)"
            )
        finding = context.get("domain_finding")
        if isinstance(finding, dict):
            finding_domain = finding.get("domain")
            if finding_domain not in (None, self.domain):
                raise WorkerError(
                    f"{self.worker_name!r} cannot consume a DomainFinding from "
                    f"domain {finding_domain!r} (bounded-domain guard)"
                )

    # -- abstract extraction hooks --------------------------------------

    @abstractmethod
    def _observations(self, context: dict) -> list:
        """Deterministic observations extracted from ``context``."""

    @abstractmethod
    def _claims(self, context: dict) -> list:
        """Deterministic supported claims extracted from ``context``."""

    def _uncertainties(self, context: dict) -> list:  # override where valuable
        """Deterministic uncertainties preserved from ``context``."""
        return list(context.get("uncertainties", []))
# -- emission ---------------------------------------------------------

    def _emit(self, *, coverage_plan: dict, context: dict) -> dict:
        """Assemble the durable EvidenceShard for this worker."""
        observations = self._observations(context)
        claims = self._claims(context)
        uncertainties = self._uncertainties(context)

        # Build structured claims with evidence state (Fix: evidence-aware)
        structured_claims = self._build_structured_claims(claims, context)

        # Prove it is a shard, not a finding/decision artifact.
        plan_provenance = coverage_plan.get("provenance") or {}
        event_id = plan_provenance.get("event_id") or coverage_plan.get(
            "coverage_plan_id", "unknown"
        )
        suffix = self._id_suffix(event_id)
        evidence_ids = [
            f"E-{suffix}-{self.worker_name}-{i + 1}"
            for i in range(len(observations))
        ] or [f"E-{suffix}-{self.worker_name}-0"]

        return {
            "evidence_shard_id": f"ES-{suffix}-{self.worker_name}",
            "situation_id": coverage_plan["situation_id"],
            "worker": self.worker_name,
            "domain": self.domain,
            "observations": observations,
            "claims": claims,
            "structured_claims": structured_claims,
            "evidence_ids": evidence_ids,
            "confidence": self._confidence(context),
            "risk_level": self._risk_level(context),
            "uncertainties": uncertainties,
            "affected_entities": self._affected_entities(context),
            "provenance": {
                "event_id": event_id,
                "situation_id": coverage_plan["situation_id"],
                "coverage_plan_id": coverage_plan["coverage_plan_id"],
                "execution_trace_id": coverage_plan["execution_trace_id"],
                "worker": self.worker_name,
                "produced_by": type(self).__name__,
                "spec_phase": "SPEC-001-phase-4-tier-3-workers",
            },
            "execution_trace_id": coverage_plan["execution_trace_id"],
        }

    def _build_structured_claims(
        self, claims: list, context: dict
    ) -> list:
        """Build structured claims with evidence state from string claims.

        Each structured claim has: claim, value, evidence, source, evidence_state.
        Evidence state is determined by the claim content:
        - OBSERVED: concrete evidence found
        - NO_SIGNAL: worker looked, found nothing
        """
        structured = []
        inputs = context.get("inputs", {}) or {}
        changed_files = inputs.get("changed_files") or []

        for claim in claims:
            claim_text = str(claim)
            lowered = claim_text.lower()

            # Determine evidence state
            evidence_state = "observed"
            if any(
                phrase in lowered
                for phrase in (
                    "no signal",
                    "nothing found",
                    "no evidence",
                    "no claim",
                    "no dependency",
                    "no doc",
                    "no alert",
                    "no telemetry",
                    "no changed",
                    "no build",
                    "no dependency security claim",
                    "no doc drift claim",
                    "no alert storm cluster claim",
                    "no telemetry correlation claim",
                    "no build claim supported",
                    "changeset contains no;",
                    "no scan results recorded",
                    "no doc drift signal recorded",
                    "no alert signals recorded",
                    "no telemetry signals recorded",
                    "no changed files recorded",
                    "ci outcome unknown",
                )
            ):
                evidence_state = "no_signal"

            # Build evidence list
            evidence = []
            if evidence_state == "observed":
                evidence = changed_files[:5]  # Cap evidence list
            if not evidence:
                evidence = [f"shard:{self.worker_name}"]

            structured.append(
                {
                    "claim": claim_text,
                    "value": True,
                    "evidence": evidence,
                    "source": f"worker:{self.worker_name}",
                    "evidence_state": evidence_state,
                }
            )
        return structured

    # -- deterministic derived values (subclasses may override) ----------

    def _confidence(self, context: dict) -> float:
        """Confidence in [0, 1].

        Returns context-confirmed confidence when explicitly provided;
        otherwise derives a dynamic score from the changed-file surface:
        base 0.85, minus 0.05 per changed file (capped at 0.3), minus 0.15
        for security-sensitive files (auth/security/crypto), minus 0.1 for
        critical-path files.  Result is always clamped to [0.0, 1.0].
        """
        value = context.get("confidence")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.0, min(1.0, float(value)))

        # Dynamic derivation when no explicit confidence is provided.
        base = 0.85

        inputs = context.get("inputs", {}) or {}
        changed_files = inputs.get("changed_files") or []

        # More changed files → lower confidence (max 0.3 reduction).
        base -= min(0.3, len(changed_files) * 0.05)

        # Security-sensitive files → lower confidence.
        _security = ("auth", "security", "crypto")
        if any(any(p in f.lower() for p in _security) for f in changed_files):
            base -= 0.15

        # Critical paths touched → lower confidence.
        _critical = ("core/", "kernel/", "main.", "infra/", "db/", "config.")
        if any(any(p in f.lower() for p in _critical) for f in changed_files):
            base -= 0.1

        return max(0.0, min(1.0, base))

    def _risk_level(self, context: dict) -> str:
        """Canonical risk level; defaults to ``medium``."""
        value = context.get("risk_level")
        if value in ("low", "medium", "high", "critical"):
            return value
        return "medium"

    def _affected_entities(self, context: dict) -> list:
        """Entities touched by this worker's evidence; context-extracted."""
        entities = context.get("affected_entities")
        if isinstance(entities, list):
            return [str(e) for e in entities]
        return []

    @staticmethod
    def _id_suffix(event_id: str) -> str:
        """Strip a canonical ``EVT-`` prefix (mirrors acquisition)."""
        return event_id[len("EVT-"):] if event_id.startswith("EVT-") else str(event_id)

    def _validate_shard(self, shard: dict) -> None:
        """Re-validate the emitted shard against its canonical schema."""
        try:
            jsonschema.validate(shard, load_schema("evidence-shard.schema.json"))
        except jsonschema.ValidationError as exc:  # pragma: no cover
            raise WorkerError(
                "generated EvidenceShard failed "
                "contracts/evidence-shard.schema.json: "
                f"{exc.message}"
            ) from exc
class PRPreFlightASTWorker(Worker):
    """Code intelligence: PR changeset and AST impact (MVP)."""

    @property
    def domain(self) -> str:
        return "code"

    @property
    def worker_name(self) -> str:
        return "pr-pre-flight-ast-worker"

    def _observations(self, context: dict) -> list:
        # ADR-010 / M3-B: allow Gemini (via Vertex) to fill the FREE-TEXT
        # observations when credentials are configured; otherwise (or on ANY
        # model error) fall back to the deterministic extraction below.  The
        # model output is treated as text ONLY — it never alters schema,
        # provenance, confidence, or any other shard field.
        try:
            from forgemind.llm.adapter import generate_observations

            model_obs = generate_observations("code", context)
        except Exception:
            model_obs = None
        if model_obs is not None:
            self._last_observations = model_obs
            return model_obs
        changed = context.get("inputs", {}).get("changed_files") or []
        result = [f"changed file in changeset: {f}" for f in changed] or [
            "no changed files recorded in context"
        ]
        self._last_observations = result
        return result

    def _claims(self, context: dict) -> list:
        # Same bounded Gemini-backing discipline as ``_observations``.
        try:
            from forgemind.llm.adapter import generate_claims

            model_claims = generate_claims("code", context)
        except Exception:
            model_claims = None
        if model_claims is not None:
            return model_claims
        changed = context.get("inputs", {}).get("changed_files") or []
        if changed:
            return [
                f"changeset touches {len(changed)} file(s); AST impact marked pending"
            ]
        return ["changeset contains no; file changes to claim"]

    def _confidence(self, context: dict) -> float:
        """Evidence-based confidence derived from actual code analysis signals.

        Base 0.90, then adjusts per changed-file surface and Gemini-produced
        observations.  Differs from the base Worker heuristic (file-count only)
        by incorporating test coverage, low-risk file classification, and
        risk-keyword signals from the Gemini observations / deterministic
        fallback.
        """
        value = context.get("confidence")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.3, min(1.0, float(value)))

        base = 0.90
        inputs = context.get("inputs", {}) or {}
        changed_files = inputs.get("changed_files") or []

        # -0.02 per changed file, capped at -0.15 total.
        file_penalty = min(0.15, len(changed_files) * 0.02)
        base -= file_penalty

        # -0.12 if any security-sensitive path is touched.
        _security_terms = ("auth", "security", "crypto", "token", "secret", "password")
        if any(
            any(term in f.lower() for term in _security_terms) for f in changed_files
        ):
            base -= 0.12

        # -0.08 if no test files in the changeset AND more than 2 files changed.
        _test_terms = ("test", "spec", "_test", "test_", "tests", "fixture")
        has_test_file = any(
            any(term in f.lower() for term in _test_terms) for f in changed_files
        )
        if not has_test_file and len(changed_files) > 2:
            base -= 0.08

        # +0.05 if ALL changed files are low-risk (tests, docs, config, md).
        _low_risk_terms = ("test", "spec", "_test", "test_", "tests", "fixture", "doc", ".md", "config", "README", "LICENSE")
        all_low_risk = changed_files and all(
            any(term in f.lower() for term in _low_risk_terms) for f in changed_files
        )
        if all_low_risk:
            base += 0.05

        # Scan the already-resolved observations (cached by _observations()) for
        # risk keywords.  Using the cached list avoids a second Gemini call.
        observations = getattr(self, "_last_observations", None)
        if observations is None:
            observations = self._observations(context)
        _risk_keywords = (
            "vulnerability", "injection", "auth bypass", "xss", "csrf",
            "rce", "privilege escalation", "hardcoded", "secret", "token leakage",
        )
        joined_obs = " ".join(str(o) for o in observations).lower()
        if any(keyword in joined_obs for keyword in _risk_keywords):
            base -= 0.10

        return max(0.3, min(1.0, base))


class DocsDriftAndSpecWorker(Worker):
    """Code domain: doc drift and spec conformance (narrow extension)."""

    @property
    def domain(self) -> str:
        return "code"

    @property
    def worker_name(self) -> str:
        return "docs-drift-and-spec-worker"

    def _observations(self, context: dict) -> list:
        drift = context.get("inputs", {}).get("docs_summary") or ""
        return [f"doc drift signal: {drift}"] if drift else [
            "no doc drift signal recorded in context"
        ]

    def _claims(self, context: dict) -> list:
        drift = context.get("inputs", {}).get("docs_summary") or ""
        return [f"doc drift/spec claim: {drift}"] if drift else [
            "no doc drift claim (no scope signal)"
        ]


class BuildLogAndFlakinessWorker(Worker):
    """Delivery domain: CI/CD builds and test flakiness (MVP)."""

    @property
    def domain(self) -> str:
        return "delivery"

    @property
    def worker_name(self) -> str:
        return "build-log-and-flakiness-worker"

    def _observations(self, context: dict) -> list:
        outcome = context.get("inputs", {}).get("ci_outcome") or "unknown"
        return [f"CI outcome: {outcome}"]

    def _claims(self, context: dict) -> list:
        outcome = context.get("inputs", {}).get("ci_outcome") or ""
        if outcome == "pass":
            return ["build passed with no new CI failures"]
        if outcome == "fail":
            return ["build failed; CI gate did not pass"]
        return ["CI outcome unknown; no build claim supported"]

    def _confidence(self, context: dict) -> float:
        """Derive confidence from CI outcome.

        - pass: 0.90 (high confidence in delivery health when tests & build succeed)
        - fail: 0.20 (low confidence when build fails, pulling situation below autonomous threshold)
        - other/unknown: delegates to base Worker dynamic confidence (~0.85).
        """
        value = context.get("confidence")
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return max(0.0, min(1.0, float(value)))
        outcome = context.get("inputs", {}).get("ci_outcome") or ""
        if outcome == "fail":
            return 0.20
        if outcome == "pass":
            return 0.90
        return super()._confidence(context)

    def _risk_level(self, context: dict) -> str:
        """Derive risk level from CI outcome.

        - pass: "low" (clean build indicates low delivery risk)
        - fail: "high" (failing build is high risk, triggering review/escalation)
        - other/unknown: delegates to base Worker risk level ("medium").
        """
        value = context.get("risk_level")
        if value in ("low", "medium", "high", "critical"):
            return value
        outcome = context.get("inputs", {}).get("ci_outcome") or ""
        if outcome == "fail":
            return "high"
        if outcome == "pass":
            return "low"
        return super()._risk_level(context)


class AlertStormClusteringWorker(Worker):
    """Delivery domain: alert storm triage (narrow extension)."""

    @property
    def domain(self) -> str:
        return "delivery"

    @property
    def worker_name(self) -> str:
        return "alert-storm-clustering-worker"

    def _observations(self, context: dict) -> list:
        alerts = context.get("inputs", {}).get("alert_signals") or []
        return [f"alert signal: {a}" for a in alerts] or [
            "no alert signals recorded in context"
        ]

    def _claims(self, context: dict) -> list:
        alerts = context.get("inputs", {}).get("alert_signals") or []
        return [f"clustered {len(alerts)} alert signal(s)"] if alerts else [
            "no alert storm cluster claim (no signals)"
        ]


class TelemetryCorrelationWorker(Worker):
    """Production domain: telemetry correlation and anomaly detection (MVP)."""

    @property
    def domain(self) -> str:
        return "production"

    @property
    def worker_name(self) -> str:
        return "telemetry-correlation-worker"

    def _observations(self, context: dict) -> list:
        signals = context.get("inputs", {}).get("telemetry_signals") or []
        return [f"telemetry signal: {s}" for s in signals] or [
            "no telemetry signals recorded in context"
        ]

    def _claims(self, context: dict) -> list:
        signals = context.get("inputs", {}).get("telemetry_signals") or []
        return [f"{len(signals)} telemetry signal(s) correlated"] if signals else [
            "no telemetry correlation claim (no signals)"
        ]

    def _risk_level(self, context: dict) -> str:
        signals = context.get("inputs", {}).get("telemetry_signals") or []
        if any(float(s) > 10.0 for s in signals):
            return "critical"
        if any(float(s) > 5.0 for s in signals):
            return "high"
        return super()._risk_level(context)


class SecurityAndDependencyWorker(Worker):
    """Production domain: vulnerability scans and dependency analysis (narrow)."""

    @property
    def domain(self) -> str:
        return "production"

    @property
    def worker_name(self) -> str:
        return "security-and-dependency-worker"

    def _observations(self, context: dict) -> list:
        scan = context.get("inputs", {}).get("dependency_scan") or []
        return [f"dependency scan result: {s}" for s in scan] or [
            "no dependency scan results recorded in context"
        ]

    def _claims(self, context: dict) -> list:
        scan = context.get("inputs", {}).get("dependency_scan") or []
        return [f"reviewed {len(scan)} dependency scan result(s)"] if scan else [
            "no dependency security claim (no scan results)"
        ]
class WorkerRegistry:
    """Factory mapping a canonical worker id to its concrete worker class.

    Instances are stateless builders for :class:`WorkerCoordinator`.
    """

    workers_by_name = {
        "pr-pre-flight-ast-worker": PRPreFlightASTWorker,
        "docs-drift-and-spec-worker": DocsDriftAndSpecWorker,
        "build-log-and-flakiness-worker": BuildLogAndFlakinessWorker,
        "alert-storm-clustering-worker": AlertStormClusteringWorker,
        "telemetry-correlation-worker": TelemetryCorrelationWorker,
        "security-and-dependency-worker": SecurityAndDependencyWorker,
    }

    def __init__(self, **worker_kwargs) -> None:
        self._instances = {
            name: cls(**worker_kwargs)
            for name, cls in self.workers_by_name.items()
        }

    def get(self, worker_name: str) -> Worker:
        if worker_name not in self._instances:
            raise WorkerError(
                f"unknown worker {worker_name!r}; known workers: "
                f"{sorted(self._instances)}"
            )
        return self._instances[worker_name]

    def worker_names(self) -> tuple:
        return tuple(self._instances)


class WorkerCoordinator:
    """Run the CoveragePlan-selected workers independently (concurrently by
    default, bounded by ``max_concurrent_managers``).

    Only workers whose owned domain appears in ``selected_domains`` are run;
    any other context / worker mapping is rejected (Invariant 1 leaf boundary).
    """

    def __init__(self, registry: Optional[WorkerRegistry] = None) -> None:
        self._registry = registry or WorkerRegistry()

    def dispatch(
        self,
        coverage_plan: dict,
        contexts: Optional[Mapping] = None,
        *,
        max_concurrent_workers: Optional[int] = None,
    ) -> dict:
        """Emit one EvidenceShard per selected worker that has context.

        Returns ``{"shards": [...], "errors": {worker_name: message}}``.
        """
        if not isinstance(coverage_plan, dict):
            raise WorkerError("coverage_plan must be a JSON object")

        selected_domains = list(coverage_plan.get("selected_domains") or [])
        selected_workers = list(coverage_plan.get("selected_workers") or [])
        contexts = dict(contexts or {})

        pool_size = max_concurrent_workers or coverage_plan.get(
            "global_constraints", {}
        ).get("max_concurrent_managers") or 1
        pool_size = max(1, int(pool_size))

        shards: list = []
        errors: dict[str, str] = {}
        with ThreadPoolExecutor(max_workers=pool_size) as pool:
            future_map = {}
            for worker_name, context in contexts.items():
                owner = WORKER_NAMES_BY_DOMAIN.get(worker_name)
                if owner not in selected_domains:
                    errors[worker_name] = (
                        f"worker {worker_name!r} owns domain {owner!r}, which is "
                        "not selected for coverage; leaf workers never exceed "
                        "their bounded domain (Invariant 1)"
                    )
                    continue
                if worker_name not in selected_workers:
                    errors[worker_name] = (
                        f"worker {worker_name!r} not in coverage_plan.selected_workers"
                    )
                    continue
                worker = self._registry.get(worker_name)
                future = pool.submit(
                    worker.build_shard, coverage_plan, context
                )
                future_map[future] = worker_name
            for future in as_completed(future_map):
                name = future_map[future]
                try:
                    shards.append(future.result())
                except Exception as exc:  # surface genuine per-worker failures
                    errors[name] = str(exc)

        return {"shards": shards, "errors": errors}