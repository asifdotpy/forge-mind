"""
ForgeMind — Hierarchical Engineering Agent Runtime DAG.

Phase 0 package scaffold: importable so contract/integration tests and the
fixture runner can validate the canonical artifacts against the Spec-Kit
JSON Schema contracts (specs/001-hierarchical-runtime-dag/contracts/).

Phase 1 (SPEC-001 T100 — Contracts & Event Acquisition): exposes
:func:`acquire_event`, implementing the deterministic lineage prefix
``Event -> CoveragePlan``.

Phase 2 (SPEC-001 T200 — Tier 1 Supervisor): exposes :class:`Supervisor`,
which wraps acquisition and emits the ``SupervisorDispatch`` trace record
(``Supervisor -> selected Managers + coverage decision``).

Phase 5 (SPEC-001 T500 — Tier 4 Cross-Lifecycle Validator): exposes
:class:`CrossLifecycleValidator`, which reconciles DomainFindings from all
selected domains into a single ``ValidatedSituation`` — the sole tier
authorized to reconcile evidence across domain boundaries, and the source
of truth consumed by the Tier 5 Decision Reducer (Phase 6).

Phase 6 (SPEC-001 T600 — Tier 5 Decision Reducer + ActionValidation +
Escalation): exposes :class:`DecisionReducer` (the sole tier authorized to
convert a ValidatedSituation into an operational decision, per ADR-006)
and the downstream safety gate — :class:`ActionValidationGate` plus
:func:`publish_terminal_output`, the structural no-bypass point through
which every terminal Action or Escalation must flow.
"""

__version__ = "0.1.0"

from forgemind._paths import (
    CONTRACTS_DIR,
    FIXTURES_EXPECTED_DIR,
    FIXTURES_INPUT_DIR,
    REPO_ROOT,
    SPEC_DIR,
)
from forgemind.acquisition import (
    EventValidationError,
    acquire_event,
    persist_artifacts,
)
from forgemind.supervisor import Supervisor, SupervisorError
from forgemind.domain_managers import (
    CodeIntelligenceManager,
    DeliveryHealthManager,
    DomainError,
    DomainManagerError,
    ManagerCoordinator,
    ManagerRegistry,
    ProductionHealthManager,
)
from forgemind.workers import (
    AlertStormClusteringWorker,
    BuildLogAndFlakinessWorker,
    DocsDriftAndSpecWorker,
    PRPreFlightASTWorker,
    SecurityAndDependencyWorker,
    TelemetryCorrelationWorker,
    Worker,
    WorkerCoordinator,
    WorkerError,
    WorkerRegistry,
)
from forgemind.validator import CrossLifecycleValidator, ValidatorError
from forgemind.reducer import (
    AUTONOMOUS_CONFIDENCE,
    ESCALATE_CONFIDENCE,
    DecisionReducer,
    ReducerError,
)
from forgemind.action_gate import (
    ActionGateError,
    ActionValidationGate,
    publish_terminal_output,
)

# SPEC-001 M2 (Cloud Run deployment prep): expose the FastAPI application
# factory.  Placed LAST on purpose — forgemind.api imports submodules
# directly (never the partially-initialized package namespace), so this
# cannot cause a circular import.  Requires fastapi/uvicorn, which are
# declared as hard dependencies in pyproject.toml.
from forgemind.api import create_api

__all__ = [
    "AUTONOMOUS_CONFIDENCE",
    "ActionGateError",
    "ActionValidationGate",
    "AlertStormClusteringWorker",
    "BuildLogAndFlakinessWorker",
    "CONTRACTS_DIR",
    "CodeIntelligenceManager",
    "CrossLifecycleValidator",
    "DecisionReducer",
    "DeliveryHealthManager",
    "DocsDriftAndSpecWorker",
    "DomainError",
    "DomainManagerError",
    "ESCALATE_CONFIDENCE",
    "EventValidationError",
    "FIXTURES_EXPECTED_DIR",
    "FIXTURES_INPUT_DIR",
    "ManagerCoordinator",
    "ManagerRegistry",
    "PRPreFlightASTWorker",
    "ProductionHealthManager",
    "REPO_ROOT",
    "SPEC_DIR",
    "SecurityAndDependencyWorker",
    "Supervisor",
    "SupervisorError",
    "TelemetryCorrelationWorker",
    "ValidatorError",
    "Worker",
    "WorkerCoordinator",
    "WorkerError",
    "WorkerRegistry",
    "acquire_event",
    "create_api",
    "persist_artifacts",
    "publish_terminal_output",
    "smoke",
]


def smoke() -> str:
    """Trivial import smoke-check for the Phase 0 scaffold."""
    return "forgemind importable"
