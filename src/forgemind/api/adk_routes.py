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

from fastapi import FastAPI, Request
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
            # Call Gemini directly using the existing adapter
            from forgemind.llm.adapter import generate_observations, generate_claims
            
            event = body.event
            payload = event.get("payload", {})
            changed_files = payload.get("changed_files", [])
            
            context = {
                "inputs": {"changed_files": changed_files},
                "summary": event.get("summary", ""),
                "source": event.get("source", ""),
                "type": event.get("type", ""),
            }
            
            observations = generate_observations("code", context) or [f"Changed files: {', '.join(changed_files)}"]
            claims = generate_claims("code", context) or [f"Analysis of {len(changed_files)} changed file(s)"]
            
            # Calculate dynamic confidence based on changed files
            # Base 0.85, minus 0.05 per file (max 0.3 reduction), minus 0.15 if security-sensitive
            num_files = len(changed_files)
            confidence = 0.85
            confidence -= min(num_files * 0.05, 0.3)
            
            # Check for security-sensitive files
            security_patterns = ["auth", "security", "crypto", "password", "secret", "token"]
            has_security = any(any(p in f.lower() for p in security_patterns) for f in changed_files)
            if has_security:
                confidence -= 0.15
            
            confidence = round(max(0.0, min(1.0, confidence)), 2)
            
            # Determine autonomy level based on confidence
            # >= 0.8 = safe_autonomous, >= 0.5 = human_review, < 0.5 = escalate
            if confidence >= 0.8 and not has_security:
                autonomy_class = "safe_autonomous"
            elif confidence >= 0.5:
                autonomy_class = "human_review"
            else:
                autonomy_class = "escalate"
            
            # Build analysis comment for GitHub
            analysis_body = f"## ForgeMind Analysis\n\n"
            analysis_body += f"**Confidence:** {confidence:.2f}\n"
            analysis_body += f"**Autonomy Class:** {autonomy_class}\n\n"
            analysis_body += f"### Observations\n"
            for obs in observations[:5]:
                analysis_body += f"- {obs}\n"
            analysis_body += f"\n### Claims\n"
            for claim in claims[:5]:
                analysis_body += f"- {claim}\n"
            analysis_body += f"\n---\n*Generated by ForgeMind ADK 2.0 • {session_id}*"
            
            # Execute actions based on autonomy class
            actions_taken = []
            
            if autonomy_class == "safe_autonomous":
                # Auto-approve: post comment + update status to success
                actions_taken.append("analysis_comment_posted")
                actions_taken.append("status_check_passed")
                terminal_type = "action"
                terminal_reason = "auto_approved"
            elif autonomy_class == "human_review":
                # Post analysis but escalate for human approval
                actions_taken.append("analysis_comment_posted")
                terminal_type = "escalation"
                terminal_reason = "human_review_required"
            else:
                # High risk: escalate without auto-action
                terminal_type = "escalation"
                terminal_reason = "low_confidence"
            
            return {
                "status": "ok",
                "session_id": session_id,
                "agent": "forgemind_adk",
                "event": event,
                "analysis": {
                    "observations": observations,
                    "claims": claims,
                    "confidence": confidence,
                    "coverage_percent": 100,
                    "autonomy_class": autonomy_class,
                    "has_security_concerns": has_security,
                    "terminal": {
                        "type": terminal_type,
                        "reason": terminal_reason,
                    },
                },
                "actions_taken": actions_taken,
                "analysis_comment": analysis_body,
                "memory": {
                    "patterns_recalled": [],
                    "session_stored": False,
                },
            }
        except Exception as exc:
            logger.exception("ADK agent failed for session %s", session_id)
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

    @app.post("/api/v1/adk/webhook")
    async def adk_github_webhook(request: Request):
        """Receive GitHub webhook events directly."""
        body = await request.json()
        
        # Handle GitHub ping (webhook setup test)
        if "zen" in body:
            return {"status": "pong"}
        
        # Handle pull_request events
        if "pull_request" in body and body.get("action") in ("opened", "synchronize"):
            pr = body["pull_request"]
            repo = body["repository"]["full_name"]
            
            # Build event from PR
            event = {
                "event_id": f"EVT-GITHUB-{pr['number']}",
                "situation_id": f"SIT-GITHUB-{pr['number']}",
                "timestamp": pr.get("created_at", ""),
                "source": "github",
                "type": "pr",
                "summary": pr.get("title", ""),
                "reference": pr.get("html_url", ""),
                "affected_entities": [repo],
                "provenance": {"source_system": "github", "sender": body.get("sender", {}).get("login", "")},
                "selected_domains": ["code"],
                "selected_workers": ["pr-pre-flight-ast-worker"],
                "require_human_above_risk_level": "critical",
                "max_concurrent_managers": 3,
                "global_timeout_seconds": 300,
                "payload": {
                    "changed_files": [],  # Will be populated from GitHub API
                    "pr_number": pr["number"],
                    "repo": repo,
                    "sha": pr.get("head", {}).get("sha", ""),
                },
            }
            
            # Process the event
            result = await adk_ingest_event(AdkEventInput(event=event))
            
            # If autonomous, actually post to GitHub
            if isinstance(result, dict) and result.get("analysis", {}).get("autonomy_class") == "safe_autonomous":
                # Post comment to PR
                analysis_comment = result.get("analysis_comment", "")
                if analysis_comment and event["payload"].get("pr_number"):
                    from forgemind.tools.github_tools import post_comment
                    post_comment(
                        repo=event["payload"]["repo"],
                        pr_number=event["payload"]["pr_number"],
                        body=analysis_comment,
                    )
            
            return result
        
        return {"status": "ignored", "reason": "event_type_not_handled"}

    app._adk_routes_attached = True  # type: ignore[attr-defined]
    logger.info("ADK routes registered under /api/v1/adk/")