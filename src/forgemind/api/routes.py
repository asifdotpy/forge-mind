from __future__ import annotations

"""FastAPI route handlers - thin HTTP mapping over pipeline + dashboard."""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse

from forgemind._paths import CONTRACTS_DIR
from forgemind.acquisition import EventValidationError
from forgemind.adk_runtime import (
    ApprovalError,
    is_adk_runtime,
    resume_adk_pipeline,
    run_adk_pipeline,
)
from forgemind.api.dashboard import DEFAULT_VIEWER_SITUATION_ID, _render_situation_html
from forgemind.api.dashboard.helpers import _esc
from forgemind.api.errors import PIPELINE_ERRORS, SERVICE_VERSION
from forgemind.api.models import ApprovalDecision, EventInput
from forgemind.api.pipeline import _fixture_body_for, run_pipeline

# ADK routes are registered lazily inside create_api() so the deterministic
# path is byte-for-byte unaffected when google-adk is not installed.
from forgemind.api.adk_routes import register_adk_routes

logger = logging.getLogger(__name__)

def _contract_not_found(name: str) -> JSONResponse:
    available = sorted(p.name for p in CONTRACTS_DIR.glob("*.json"))
    return JSONResponse(
        status_code=404,
        content={
            "error": "not_found",
            "detail": f"unknown contract {name!r}",
            "available": available,
        },
    )


def create_api() -> FastAPI:
    """Build the ForgeMind FastAPI application (uvicorn ``--factory`` target)."""
    app = FastAPI(
        title="ForgeMind Control Plane",
        version=SERVICE_VERSION,
        description=(
            "Autonomous engineering control plane running the five-tier DAG: "
            "Supervisor, Domain Managers, Specialist Workers, "
            "Cross-Lifecycle Validator, Decision Reducer."
        ),
    )

    @app.get("/api/v1/health")
    async def health() -> Dict[str, Any]:
        """Liveness probe target for Cloud Run startup/liveness checks."""
        return {
            "status": "ok",
            "service": "forge-mind",
            "version": SERVICE_VERSION,
            "phases_complete": 6,
        }

    @app.post("/api/v1/events")
    async def ingest_event(body: EventInput):
        """Ingest an Event, run the full five-tier pipeline, and return the
        terminal outcome plus every intermediate artifact."""
        try:
            if is_adk_runtime():
                return run_adk_pipeline(body)
            return run_pipeline(body)
        except EventValidationError as exc:
            logger.warning("event validation failed: %s", exc)
            return JSONResponse(
                status_code=422,
                content={"error": "validation_error", "detail": str(exc)},
            )
        except PIPELINE_ERRORS as exc:
            logger.exception("pipeline failure while processing event")
            return JSONResponse(
                status_code=500,
                content={"error": "pipeline_error", "detail": str(exc)},
            )

    @app.get("/api/v1/situations/{situation_id}")
    async def get_situation(situation_id: str, body: Optional[EventInput] = None):
        """Return the situation view (artifacts + M3 proof) for ``situation_id``.

        The runtime is stateless — there is no artifact store — so the
        situation is re-derived: either from a posted ``EventInput`` body
        (identical envelope to ``POST /api/v1/events``) or, when no body is
        supplied, by replaying the canonical repository fixture whose Event
        carries this ``situation_id``.
        """
        request_body = body or _fixture_body_for(situation_id)
        if request_body is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "not_found",
                    "detail": (
                        f"no replayable event for situation {situation_id!r}; "
                        "post the Event envelope to re-derive it"
                    ),
                },
            )
        try:
            return run_pipeline(request_body)
        except EventValidationError as exc:
            return JSONResponse(
                status_code=422,
                content={"error": "validation_error", "detail": str(exc)},
            )
        except PIPELINE_ERRORS as exc:
            logger.exception("pipeline failure while deriving situation")
            return JSONResponse(
                status_code=500,
                content={"error": "pipeline_error", "detail": str(exc)},
            )

    @app.get("/", response_class=HTMLResponse)
    @app.get("/view/{situation_id}", response_class=HTMLResponse)
    async def situation_viewer(situation_id: str = DEFAULT_VIEWER_SITUATION_ID):
        """Read-only, offline HTML viewer for the four M3 proof properties."""
        request_body = _fixture_body_for(situation_id)
        if request_body is None:
            return HTMLResponse(
                status_code=404,
                content=(
                    "<!DOCTYPE html><html><body><h1>Unknown situation</h1>"
                    f"<p>No replayable event for {_esc(situation_id)}.</p>"
                    "</body></html>"
                ),
            )
        try:
            result = run_pipeline(request_body)
        except (EventValidationError, *PIPELINE_ERRORS) as exc:
            return HTMLResponse(
                status_code=500,
                content=(
                    "<!DOCTYPE html><html><body><h1>Pipeline error</h1>"
                    f"<p>{_esc(exc)}</p></body></html>"
                ),
            )
        return HTMLResponse(content=_render_situation_html(result))

    @app.get("/api/v1/specs")
    async def list_specs() -> Dict[str, Any]:
        """List the canonical JSON Schema contracts (SPEC-001)."""
        contracts = []
        for path in sorted(CONTRACTS_DIR.glob("*.schema.json")):
            schema = json.loads(path.read_text(encoding="utf-8"))
            contracts.append(
                {
                    "name": path.name,
                    "title": schema.get("title"),
                    "description": schema.get("description"),
                }
            )
        return {"count": len(contracts), "contracts": contracts}

    @app.get("/api/v1/specs/{name}")
    async def get_spec(name: str):
        """Return one canonical contract schema by filename (e.g.
        ``event.schema.json``)."""
        # Path-traversal guard: bare filenames only.
        if Path(name).name != name or not name.endswith(".json"):
            return _contract_not_found(name)
        path = CONTRACTS_DIR / name
        if not path.is_file():
            return _contract_not_found(name)
        return {
            "name": name,
            "contract": json.loads(path.read_text(encoding="utf-8")),
        }

    @app.post("/api/v1/approvals/{token}")
    async def approve(token: str, decision: ApprovalDecision):
        """Human-approval resume endpoint for the ADK M3-B pause gate.

        A workflow PAUSED at the ``human_approval`` node (because the Action
        Validation gate returned ``requires_human``) exposes a
        ``pending_approval.token`` and this resume endpoint.  Posting
        ``{"decision": "approve"}`` publishes the gated outcome; posting
        ``{"decision": "reject"}`` records an Escalation and publishes no
        action.  Under the default ``deterministic`` runtime this endpoint is
        inert and returns 404 (no workflows are ever paused there).
        """
        if not is_adk_runtime():
            return JSONResponse(
                status_code=404,
                content={
                    "error": "not_found",
                    "detail": (
                        "human-approval resume is only available when "
                        "FORGEMIND_RUNTIME=adk"
                    ),
                },
            )
        try:
            return resume_adk_pipeline(token, decision.decision)
        except ApprovalError as exc:
            return JSONResponse(
                status_code=404,
                content={"error": "not_found", "detail": str(exc)},
            )

    # Register ADK 2.0 integration routes under /api/v1/adk/.
    # Idempotent and safe when google-adk is not installed.
    register_adk_routes(app)

    return app


#: Module-level ASGI app (convenience alternative to ``--factory`` usage).
app = create_api()
