"""ForgeMind Change 2 — self-contained events via deterministic worker contexts.

Derives per-worker Tier-3 ``EvidenceShard`` contexts from the inbound event's
``payload`` for the CoveragePlan's ``selected_workers``, so a raw event posted
without a hand-rolled ``workers`` key is still analyzed automatically.

This module is runtime-only.  Per ADR-009 it must not import the external
vector-store client used by development-time SpecForge tooling: the boundary
is machine-enforced by ``tests/contract/test_runtime_boundary.py``, which
blocks that import at the sys.meta_path level for every runtime module.
"""

from __future__ import annotations

from typing import Any, Dict

from forgemind.workers import WORKER_NAMES_BY_DOMAIN

__all__ = ["build_worker_contexts"]

#: payload key -> worker id.  In every case the worker's ``inputs`` key equals
#: the payload key (docs/ARCHITECTURE.md Tier 3 + workers.py input contract).
_PAYLOAD_KEY_TO_WORKER = {
    "changed_files": "pr-pre-flight-ast-worker",
    "ci_outcome": "build-log-and-flakiness-worker",
    "docs_summary": "docs-drift-and-spec-worker",
    "alert_signals": "alert-storm-clustering-worker",
    "telemetry_signals": "telemetry-correlation-worker",
    "dependency_scan": "security-and-dependency-worker",
}


def build_worker_contexts(event: dict, coverage_plan: dict) -> dict:
    """Derive deterministic per-worker contexts from ``event.payload``.

    For each ``coverage_plan["selected_workers"]`` worker that has a matching
    payload key present, emit ``{"domain": <worker.domain>, "inputs": {<key>:
    <value>}}``.  Workers not selected, or with no matching payload key, are
    omitted entirely.

    Every emitted context honors the Tier-3 ``_assert_bounded_context``
    contract by setting ``domain`` to the worker's owned domain.  Derivation is
    a pure function of ``event`` + ``coverage_plan``: no wall clock, no
    randomness — replay-stable (identical inputs yield identical mappings).

    Args:
        event: normalized Event dict (must carry ``payload``).
        coverage_plan: the Tier 1 ``CoveragePlan`` that selected the workers.

    Returns:
        A mapping ``{worker_name: context}`` suitable for
        ``WorkerCoordinator().dispatch(coverage_plan, contexts)``.  May be
        empty when the event's payload carries none of the known keys or no
        matching worker was selected.
    """
    payload = event.get("payload") or {}
    selected_workers = set(coverage_plan.get("selected_workers") or [])

    #: Workers that consume the monitoring status channel (ADR-013).  When the
    #: monitoring source is unavailable they must emit UNAVAILABLE evidence,
    #: so ``monitoring_state`` is forwarded alongside their signal lists.
    _MONITORING_AWARE_WORKERS = {
        "alert-storm-clustering-worker",
        "telemetry-correlation-worker",
    }

    contexts: Dict[str, Any] = {}
    for key, worker_name in _PAYLOAD_KEY_TO_WORKER.items():
        if worker_name not in selected_workers:
            continue
        domain = WORKER_NAMES_BY_DOMAIN.get(worker_name)
        if domain is None:  # defensive: canonical map is authoritative
            continue
        inputs = {key: payload[key]} if key in payload else {}
        # Forward changed_files alongside the worker's own signal so
        # confidence derivation that scales with the changeset surface (base
        # Worker._confidence) computes evidence-based values.  Workers with
        # no matching payload key are still omitted entirely -- changed_files
        # alone never fabricates a context.
        if "changed_files" in payload and key in payload:
            inputs.setdefault("changed_files", payload["changed_files"])
        if worker_name in _MONITORING_AWARE_WORKERS and "monitoring_state" in payload:
            inputs["monitoring_state"] = payload["monitoring_state"]
        contexts[worker_name] = {
            "domain": domain,
            "inputs": inputs,
        }
    return contexts