"""FastAPI routes for the ADK 2.0 integration layer.

This module exposes the ADK runner behind a dedicated ``/api/v1/adk/``
prefix so it coexists with the existing deterministic routes
(``/api/v1/events``, ``/api/v1/health``) without conflict.

All ADK imports are lazy: the routes register and respond even when
``google-adk`` is not installed (with a clear 503-style response rather
than an import error), so local dev is never blocked.

Routes:
    POST /api/v1/adk/events          Ingest an event, run it through ADK agents
    POST /api/v1/adk/sessions/{id}/resume  Resume a paused workflow
    GET  /api/v1/adk/sessions/{id}   Get session state
    GET  /api/v1/adk/agents          List registered agents (discovery)
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from forgemind.adk_app import create_adk_runner, describe_adk_agents

logger = logging.getLogger(__name__)


# -- Request envelopes -----------------------------------------------

class AdkEventInput(BaseModel):
    """Request envelope for ``POST /api/v1/adk/events``."""

    model_config = ConfigDict(extra="ignore")

    event: Dict[str, Any]
    session_id: Optional[str] = None


class AdkResumeInput(BaseModel):
    """Request envelope for ``POST /api/v1/adk/sessions/{id}/resume``."""

    model_config = ConfigDict(extra="ignore")

    decision: str = "approve"  # approve | reject


# -- Lazy runner singleton ------------------------------------------

_runner: Any = None


def _get_runner() -> Any:
    """Return (and memoise) the ADK runner, building it on first use.

    Returns ``None`` when google-adk is not importable.
    """
    global _runner
    if _runner is None:
        _runner = create_adk_runner()
    return _runner


# -- In-memory session store (demo affordance) ----------------------
# Maps opaque session_id -> paused workflow context.  Stateless across
# process restarts (same model as forgemind.adk_runtime._PENDING_APPROVALS).
_ADK_PAUSED: Dict[str, Dict[str, Any]] = {}


# -- Route registration ---------------------------------------------

def register_adk_routes(app: FastAPI) -> None:
    """Attach the ADK routes to an existing FastAPI application.

    Idempotent: calling twice on the same app is a no-op.
    """
    if getattr(app, "_adk_routes_attached", False):
        return

    @app.post("/api/v1/adk/events")
    async def adk_ingest_event(body: AdkEventInput):
        """Ingest an Event and run it through the ADK agent graph.

        When google-adk is not installed, returns HTTP 503 with a clear
        message rather than an import error.
        """
        runner = _get_runner()
        if runner is None:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "adk_unavailable",
                    "detail": (
                        "google-adk is not installed. Install with "
                        "`uv pip install google-adk>=2.0.0` and restart."
                    ),
                },
            )

        session_id = body.session_id or uuid.uuid4().hex
        try:
            from google.genai import types as adk_types

            user_content = adk_types.Content(
                role="user",
                parts=[adk_types.Part(text=str(body.event))],
            )
            session_service = runner.session_service

            # Ensure the session exists.
            try:
                session_service.get_session(
                    app_name=runner.app_name,
                    user_id="anonymous",
                    session_id=session_id,
                )
            except Exception:
                # Session doesn't exist yet — create it.
                import asyncio
                asyncio.run(session_service.create_session(
                    app_name=runner.app_name,
                    user_id="anonymous",
                    session_id=session_id,
                ))

            import asyncio

            async def run_agent():
                events = []
                async for event in runner.run_async(
                    user_id="anonymous",
                    session_id=session_id,
                    new_message=user_content,
                ):
                    events.append(event.model_dump() if hasattr(event, "model_dump") else str(event))
                return events

            events = asyncio.run(run_agent())

            return {
                "status": "ok",
                "session_id": session_id,
                "events": events,
            }
        except ImportError:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "adk_unavailable",
                    "detail": (
                        "google-adk types module not importable. "
                        "Check your google-adk installation."
                    ),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("ADK runner failed for session %s", session_id)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "adk_runner_error",
                    "detail": str(exc),
                    "session_id": session_id,
                },
            )

    @app.post("/api/v1/adk/sessions/{session_id}/resume")
    async def adk_resume_session(session_id: str, body: AdkResumeInput):
        """Resume a paused ADK workflow after a human decision."""
        runner = _get_runner()
        if runner is None:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "adk_unavailable",
                    "detail": "google-adk is not installed.",
                },
            )

        pending = _ADK_PAUSED.pop(session_id, None)
        if pending is None:
            return JSONResponse(
                status_code=404,
                content={
                    "error": "not_found",
                    "detail": (
                        f"no paused ADK workflow for session {session_id!r}; "
                        "the workflow is not paused or was already resumed."
                    ),
                },
            )

        decision = (body.decision or "").lower()
        if decision not in ("approve", "reject"):
            # Do not consume the pending state on a bad request.
            _ADK_PAUSED[session_id] = pending
            return JSONResponse(
                status_code=400,
                content={
                    "error": "invalid_decision",
                    "detail": f"decision must be 'approve' or 'reject', got {decision!r}",
                },
            )

        return {
            "status": "resumed",
            "session_id": session_id,
            "decision": decision,
            "resumed_from": pending,
        }

    @app.get("/api/v1/adk/sessions/{session_id}")
    async def adk_get_session(session_id: str):
        """Return the current state of an ADK session."""
        runner = _get_runner()
        if runner is None:
            return JSONResponse(
                status_code=503,
                content={
                    "error": "adk_unavailable",
                    "detail": "google-adk is not installed.",
                },
            )

        try:
            session_service = runner.session_service
            session = session_service.get_session(
                app_name=runner.app_name,
                user_id="anonymous",
                session_id=session_id,
            )
            return {
                "session_id": session_id,
                "state": session.model_dump() if hasattr(session, "model_dump") else str(session),
            }
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                status_code=404,
                content={
                    "error": "not_found",
                    "detail": f"session {session_id!r} not found: {exc}",
                },
            )

    @app.get("/api/v1/adk/agents")
    async def adk_list_agents():
        """List registered ADK agents (discovery endpoint)."""
        agents = describe_adk_agents()
        return {
            "count": len(agents),
            "agents": [
                {"name": name, "description": desc}
                for name, desc in agents.items()
            ],
        }

    app._adk_routes_attached = True  # type: ignore[attr-defined]
    logger.info("ADK routes registered under /api/v1/adk/")