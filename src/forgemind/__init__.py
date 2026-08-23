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

__all__ = [
    "AlertStormClusteringWorker",
    "BuildLogAndFlakinessWorker",
    "CONTRACTS_DIR",
    "CodeIntelligenceManager",
    "DeliveryHealthManager",
    "DocsDriftAndSpecWorker",
    "DomainError",
    "DomainManagerError",
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
    "Worker",
    "WorkerCoordinator",
    "WorkerError",
    "WorkerRegistry",
    "acquire_event",
    "persist_artifacts",
    "smoke",
]


def smoke() -> str:
    """Trivial import smoke-check for the Phase 0 scaffold."""
    return "forgemind importable"
