from __future__ import annotations

"""ForgeMind HTTP API package (modularised from the former single file).

Facade module - re-exports the exact public surface the single-file
``forgemind.api`` exposed, so ``uvicorn forgemind.api:create_api``, the
package ``__init__`` binding, the Dockerfile, and the contract tests all
keep working with zero changes.

Typical request flow is a *thin* wrapper over the five-tier DAG that ``scripts/run_fixture.py`` already exercises: Acquire -> Supervisor -> Workers -> Managers -> Validator -> Reducer -> ActionGate -> publish.
"""
from forgemind.api.dashboard import (
    DEFAULT_VIEWER_SITUATION_ID,
    _render_situation_html,
)
from forgemind.api.errors import PIPELINE_ERRORS, SERVICE_VERSION
from forgemind.api.models import ApprovalDecision, EventInput
from forgemind.api.pipeline import _fixture_body_for, run_pipeline
from forgemind.api.routes import app, create_api
from forgemind.api.adk_routes import register_adk_routes

__all__ = [
    "ApprovalDecision",
    "DEFAULT_VIEWER_SITUATION_ID",
    "EventInput",
    "PIPELINE_ERRORS",
    "SERVICE_VERSION",
    "_fixture_body_for",
    "_render_situation_html",
    "app",
    "create_api",
    "register_adk_routes",
    "run_pipeline",
]
