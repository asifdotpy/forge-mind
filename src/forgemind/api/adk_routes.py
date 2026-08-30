"""FastAPI routes for the ADK 2.0 integration layer.

This module exposes the ADK integration behind a dedicated ``/api/v1/adk/``
prefix so it coexists with the existing deterministic routes
(``/api/v1/events``, ``/api/v1/health``) without conflict.

Event ingestion (``POST /api/v1/adk/events``) drives the real hierarchical ADK
DAG (:func:`forgemind.adk_runtime.run_adk_pipeline`) — Acquire -> Supervisor ->
Managers -> Workers -> Validator -> Reducer -> human_approval -> Action Gate —
and returns the genuine artifacts plus ``m3_proof`` (with the authoritative
``human_control_state`` autonomy signal).  This path is stdlib-only, so it
works without ``google-adk`` and in Cloud Run.

The ``google.adk.Runner`` remains available as a discovery / session-memory
surface (``GET /api/v1/adk/agents``, ``GET /api/v1/adk/sessions/...``) but is
NOT the decision-execution graph; the hierarchical DAG above is authoritative.

All ADK imports are lazy: the routes register and respond even when
``google-adk`` is not installed.

Routes:
    POST /api/v1/adk/events          Run an event through the hierarchical DAG
    POST /api/v1/adk/sessions/{id}/resume  Resume a paused workflow
    GET  /api/v1/adk/sessions/{id}   Get session state
    GET  /api/v1/adk/agents          List registered agents (discovery)
    POST /api/v1/adk/webhook         GitHub webhook receiver
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from forgemind.acquisition import EventValidationError
from forgemind.adk_app import create_adk_runner, describe_adk_agents
from forgemind.adk_runtime import run_adk_pipeline
from forgemind.api.errors import PIPELINE_ERRORS
from forgemind.situation_store import SituationStore

logger = logging.getLogger(__name__)


# -- Request envelopes -----------------------------------------------

class AdkEventInput(BaseModel):
    """Request envelope for ``POST /api/v1/adk/events``.

    Only ``event`` is required, mirroring ``forgemind.api.EventInput``: the
    optional ``workers`` / ``evidence_shards`` / ``domain_findings`` keys let
    callers supply pre-computed Tier-3/Tier-2 artifacts so the full autonomy
    range (including ``safe_autonomous``) can be exercised through the real
    hierarchical DAG.  When omitted, the self-sufficient worker-context path
    runs instead.
    """

    model_config = ConfigDict(extra="ignore")

    event: Dict[str, Any]
    session_id: Optional[str] = None
    workers: Optional[Dict[str, Any]] = None
    evidence_shards: Optional[List[Dict[str, Any]]] = None
    domain_findings: Optional[List[Dict[str, Any]]] = None


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


# -- Response-envelope helpers --------------------------------------
# The authoritative execution path for an ingested event is the hierarchical
# ADK DAG (:func:`forgemind.adk_runtime.run_adk_pipeline`), which produces the
# genuine artifacts + ``m3_proof`` (with the ``human_control_state`` autonomy
# signal and the full trajectory lineage).  The envelope below surfaces that
# signal at a stable top-level ``autonomy`` key plus a GitHub-ready
# ``analysis_comment``, and derives ``actions_taken`` from the autonomy class.

def _actions_for_autonomy(autonomy_class: Optional[str]) -> list:
    """Map the reducer's autonomy class onto the executed-action labels."""
    if autonomy_class == "safe_autonomous":
        return ["analysis_comment_posted", "status_check_passed"]
    if autonomy_class == "human_review":
        return ["analysis_comment_posted"]
    return []


def _webhook_changed_files(repo: str, pr_number: int) -> list:
    """Best-effort fetch of a PR's changed filenames for the webhook.

    Degrades silently to an empty list when GITHUB_TOKEN is not configured or
    the GitHub API call fails — the hierarchical DAG still runs on whatever
    payload keys are present.
    """
    try:
        from forgemind.tools.github_tools import get_changed_files

        files = get_changed_files(repo, pr_number)
        if isinstance(files, list) and files and not files[0].get("error"):
            return [
                f.get("filename", "")
                for f in files
                if isinstance(f, dict) and f.get("filename")
            ]
    except Exception:  # noqa: BLE001
        logger.debug("webhook changed_files lookup failed", exc_info=True)
    return []


def _execute_github_actions(event: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    """Actually perform the GitHub actions the autonomy ladder selected.

    The response envelope derives ``actions_taken`` from the reducer's
    autonomy class (via :func:`_actions_for_autonomy`); this function executes
    exactly those actions so the envelope is not just decorative:

    - ``analysis_comment_posted``  -> post the analysis comment on the PR
      (non-destructive; fires for both ``safe_autonomous`` and ``human_review``).
    - ``status_check_passed``      -> mark the head commit's ``forgemind``
      status ``success`` (autonomous only).

    Each tool returns a dict; on a missing/invalid token it returns
    ``{"error": "GITHUB_TOKEN not configured"}`` which is logged and surfaced
    in the returned ``actions_result`` so a blocked write is visible rather
    than silently swallowed.
    """
    actions = (result or {}).get("actions_taken", []) or []
    payload = (event or {}).get("payload", {}) or {}
    repo = payload.get("repo")
    pr_number = payload.get("pr_number")
    sha = payload.get("sha")

    executed: Dict[str, Any] = {}

    if "analysis_comment_posted" in actions and repo and pr_number:
        from forgemind.tools.github_tools import post_comment

        comment = (result or {}).get("analysis_comment") or ""
        if comment:
            executed["analysis_comment_posted"] = post_comment(
                repo=repo, pr_number=pr_number, body=comment
            )
        else:
            executed["analysis_comment_posted"] = {"skipped": "no analysis_comment"}

    if "status_check_passed" in actions and repo and sha:
        from forgemind.tools.github_tools import update_status_check

        executed["status_check_passed"] = update_status_check(
            repo=repo,
            sha=sha,
            state="success",
            description="ForgeMind autonomous analysis passed",
            context="forgemind",
        )

    for action, outcome in executed.items():
        if isinstance(outcome, dict) and outcome.get("error"):
            logger.warning("GitHub action %s blocked: %s", action, outcome["error"])

    return executed


def _analysis_comment_from(result: Dict[str, Any]) -> str:
    """Render a Markdown analysis comment from the real pipeline result.

    Everything here is derived from authoritative artifacts — the reducer's
    autonomy/risk and the gate's verdict — never from ``changed_files`` count.
    """
    m3 = result.get("m3_proof") or {}
    control = m3.get("human_control_state") or {}
    verdict = m3.get("validation_verdict") or {}
    uncertainty = m3.get("uncertainty_summary") or {}
    terminal = result.get("terminal") or {}

    confidence = uncertainty.get("confidence")
    reasoning_path = result.get("situation_id")

    lines = [
        "## ForgeMind Analysis",
        "",
        f"**Status:** {result.get('status', 'ok')}",
        f"**Situation:** {reasoning_path or 'n/a'}",
        f"**Autonomy Class:** {control.get('autonomy_class') or 'n/a'}",
        f"**Human Control:** {control.get('state') or 'n/a'}",
        f"**Confidence:** {round(confidence, 2) if isinstance(confidence, (int, float)) else 'n/a'}",
        f"**Risk Level:** {control.get('risk_level') or 'n/a'}",
        f"**Verdict:** {verdict.get('state') or 'n/a'}",
    ]

    if terminal.get("type") in ("action", "escalation"):
        action_validation = terminal.get("action_validation") or {}
        escalation = terminal.get("escalation") or {}
        reason = (
            action_validation.get("reason")
            or escalation.get("reason")
            or "n/a"
        )
        lines.append(f"**Terminal:** {terminal.get('type')}")
        lines.append(f"**Reason:** {reason}")

    lines.append("")

    # Add approval link if pending_approval exists
    pending = result.get("pending_approval") or {}
    token = pending.get("token")
    situation_id = result.get("situation_id", reasoning_path or "")
    if token:
        service_url = os.environ.get("FORGEMIND_SERVICE_URL", "https://forgemind-n3nupsii5a-uc.a.run.app")
        approve_url = f"{service_url}/api/v1/approvals/{token}"
        view_url = f"{service_url}/view/{situation_id}"
        lines.append(f"[Review & Approve]({approve_url}) | [View Analysis]({view_url})")
        lines.append("")

    lines.append("[ForgeMind Dashboard](https://forgemind-n3nupsii5a-uc.a.run.app/)")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by ForgeMind hierarchical ADK DAG*")
    return "\n".join(lines)


def _render_adk_response(
    event: Dict[str, Any],
    session_id: str,
    result: Dict[str, Any],
) -> Dict[str, Any]:
    """Project the hierarchical-DAG result onto the /adk/events envelope.

    ``result`` is the dict returned by ``run_adk_pipeline``; its ``m3_proof``
    block is already computed, so the autonomy signal here is authoritative.
    """
    m3 = result.get("m3_proof") or {}
    control = m3.get("human_control_state") or {}
    uncertainty = m3.get("uncertainty_summary") or {}

    autonomy_class = control.get("autonomy_class")
    status = result.get("status", "ok")

    return {
        "status": status,
        "session_id": session_id,
        "agent": "forgemind_hierarchical_dag",
        "event": event,
        "situation_id": result.get("situation_id"),
        "trace_id": result.get("trace_id"),
        "autonomy": {
            "autonomy_class": autonomy_class,
            "risk_level": control.get("risk_level"),
            "confidence": uncertainty.get("confidence"),
            "human_control_state": control.get("state"),
            "requires_human": status == "paused",
        },
        "terminal": result.get("terminal"),
        "pending_approval": result.get("pending_approval"),
        "artifacts": result.get("artifacts"),
        "m3_proof": m3,
        "analysis_comment": _analysis_comment_from(result),
        "actions_taken": _actions_for_autonomy(autonomy_class),
        "memory": {
            "patterns_recalled": [],
            "session_stored": False,
        },
    }


# -- Route registration ---------------------------------------------

def register_adk_routes(app: FastAPI) -> None:
    """Attach the ADK routes to an existing FastAPI application.

    Idempotent: calling twice on the same app is a no-op.
    """
    if getattr(app, "_adk_routes_attached", False):
        return

    @app.post("/api/v1/adk/events")
    async def adk_ingest_event(body: AdkEventInput):
        """Ingest an Event and run it through the real hierarchical ADK DAG.

        Executes :func:`forgemind.adk_runtime.run_adk_pipeline`, which drives
        the genuine graph over the existing tiers -- Acquire -> Supervisor ->
        Managers -> Workers -> Validator -> Reducer -> human_approval ->
        Action Gate -- with the documented autonomy ladder and pause/resume
        gate.  This path is stdlib-only (no google-adk required) and produces
        the full artifact trajectory plus ``m3_proof``.

        When the Action Validation gate decides the proposed action needs a
        human, the workflow PAUSES: the response ``status`` is ``"paused"``
        and ``pending_approval.token`` is the resume key (post it to
        ``POST /api/v1/approvals/{token}``).
        """
        session_id = body.session_id or uuid.uuid4().hex
        try:
            # Drive the real five-tier hierarchy. ``EventInput`` only needs
            # ``event``: when no explicit workers/evidence_shards/domain_findings
            # are supplied, the self-sufficient worker-context path derives
            # per-worker evidence from the payload.
            from forgemind.api.models import EventInput

            pipeline_result = run_adk_pipeline(
                EventInput(
                    event=body.event,
                    workers=body.workers,
                    evidence_shards=body.evidence_shards,
                    domain_findings=body.domain_findings,
                )
            )
        except EventValidationError as exc:
            logger.warning("ADK event validation failed: %s", exc)
            return JSONResponse(
                status_code=422,
                content={"error": "validation_error", "detail": str(exc)},
            )
        except PIPELINE_ERRORS as exc:
            logger.exception("ADK pipeline failure for session %s", session_id)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "pipeline_error",
                    "detail": str(exc),
                    "session_id": session_id,
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("ADK agent failed for session %s", session_id)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "adk_runner_error",
                    "detail": str(exc),
                    "session_id": session_id,
                },
            )

        return _render_adk_response(body.event, session_id, pipeline_result)
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
            from forgemind.enrichment import enrich_payload

            pr = body["pull_request"]
            repo = body["repository"]["full_name"]
            pr_number = pr["number"]
            sha = pr.get("head", {}).get("sha", "")

            # Enrich payload from GitHub API (changed files, CI outcome, docs summary, dependency scan, monitoring state)
            payload = await enrich_payload(repo=repo, pr_number=pr_number, sha=sha)

            # Coverage domains are derived from the changed files (ADR-014):
            # the enriched payload already carries classifier-derived
            # ``affected_domains`` (never the brute-forced triple).
            from forgemind.acquisition import _WORKERS_BY_DOMAIN

            derived_domains = payload.get("affected_domains") or ["code"]
            derived_workers = [
                w
                for domain in derived_domains
                for w in _WORKERS_BY_DOMAIN.get(domain, ())
            ]

            # Build event from PR
            event = {
                "event_id": f"EVT-GITHUB-{pr_number}",
                "situation_id": f"SIT-GITHUB-{pr_number}",
                "timestamp": pr.get("created_at", ""),
                "source": "github",
                "type": "pr",
                "summary": pr.get("title", ""),
                "reference": pr.get("html_url", ""),
                "affected_entities": [repo],
                "provenance": {"source_system": "github", "sender": body.get("sender", {}).get("login", "")},
                "selected_domains": derived_domains,
                "selected_workers": derived_workers,
                "require_human_above_risk_level": "critical",
                "max_concurrent_managers": 3,
                "global_timeout_seconds": 300,
                "payload": payload,
            }

            # Process the event
            result = await adk_ingest_event(AdkEventInput(event=event))
            if isinstance(result, dict):
                # Store situation for dashboard viewing
                SituationStore.save(
                    situation_id=result.get("situation_id", f"SIT-GITHUB-{pr_number}"),
                    event=event,
                    result=result,
                )
                # Execute exactly the actions autonomy selected (comment for
                # safe_autonomous + human_review; status check for autonomous).
                result["actions_result"] = _execute_github_actions(event, result)
            return result
        
        return {"status": "ignored", "reason": "event_type_not_handled"}

    app._adk_routes_attached = True  # type: ignore[attr-defined]
    logger.info("ADK routes registered under /api/v1/adk/")
