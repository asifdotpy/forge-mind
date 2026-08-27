from __future__ import annotations

"""API-level constants: the service version + pipeline-failure tuple."""
from forgemind.action_gate import ActionGateError
from forgemind.domain_managers import DomainManagerError
from forgemind.reducer import ReducerError
from forgemind.supervisor import SupervisorError
from forgemind.validator import ValidatorError
from forgemind.workers import WorkerError

#: Bumped together with the package version (pyproject.toml [project.version]).
SERVICE_VERSION = "0.1.0"

#: Tier error classes that mean the pipeline itself failed (server-side 500).
PIPELINE_ERRORS = (
    SupervisorError,
    DomainManagerError,
    WorkerError,
    ValidatorError,
    ReducerError,
    ActionGateError,
)
