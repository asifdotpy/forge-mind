from __future__ import annotations

"""FastAPI route handlers - thin HTTP mapping over pipeline + dashboard."""
import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

from forgemind._env import load_dotenv
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


def _approval_page_html(token: str) -> str:
    """Render the approval page for a pending token."""
    # Get situation context if available
    situation = SituationStore.get(token)
    context_html = ""
    if situation:
        event = situation.get("event", {})
        pr = event.get("payload", {}).get("pull_request", {})
        title = pr.get("title", "Unknown PR")
        context_html = f"""
        <div class="context">
        <h2>Pull Request</h2>
        <p><strong>{_esc(title)}</strong></p>
        </div>
        """
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ForgeMind · Approval Required</title>
<style>
:root {{ color-scheme: dark; --bg:#09090b; --surface:#111113; --surface-2:#18181b;
  --border:#27272a; --text:#fafafa; --text-2:#a1a1aa; --muted:#71717a;
  --ok:#34d399; --danger:#f87171; --info:#60a5fa; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font:15px/1.55 ui-sans-serif,system-ui,sans-serif; }}
.wrap {{ max-width:600px; margin:0 auto; padding:2rem 1.5rem; }}
.card {{ background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:1.5rem; margin-bottom:1rem; }}
h1 {{ margin:0 0 .5rem; font-size:1.3rem; }}
h2 {{ margin:0 0 .5rem; font-size:1rem; color:var(--text-2); }}
p {{ color:var(--text-2); margin:0 0 1rem; }}
.approval {{ display:flex; gap:.75rem; margin:1rem 0; }}
.btn {{ display:inline-flex; align-items:center; gap:.4rem;
  font-size:.9rem; font-weight:600; padding:.6rem 1.2rem;
  border-radius:8px; text-decoration:none; cursor:pointer; }}
.btn-approve {{ color:var(--ok); border:1px solid var(--ok); background:rgba(52,211,153,.09); }}
.btn-reject {{ color:var(--danger); border:1px solid rgba(248,113,113,.45); background:rgba(248,113,113,.09); }}
.token {{ font-family:ui-monospace,monospace; font-size:.75rem; color:var(--info);
  background:var(--surface-2); padding:.5rem; border-radius:6px;
  word-break:break-all; margin-top:1rem; }}
textarea {{ width:100%; min-height:80px; background:var(--surface-2);
  border:1px solid var(--border); border-radius:8px; padding:.6rem;
  color:var(--text); font-size:.85rem; resize:vertical; margin-top:.5rem; }}
label {{ display:block; font-size:.75rem; color:var(--muted); margin-top:.8rem; }}
</style>
</head>
<body>
<div class="wrap">
<div class="card">
<h1>ForgeMind — Approval Required</h1>
<p>A proposed action is awaiting your review. Please approve or reject.</p>
{context_html}
<form method="POST" action="/api/v1/approvals/{_esc(token)}/form">
<label for="comment">Reviewer Comments (optional)</label>
<textarea id="comment" name="comment" placeholder="Add your reasoning, concerns, or conditions for this decision..."></textarea>
<div class="approval">
<button type="submit" name="decision" value="approve" class="btn btn-approve">✓ Approve</button>
<button type="submit" name="decision" value="reject" class="btn btn-reject">✕ Reject</button>
</div>
</form>
<div class="token">Token: {_esc(token)}</div>
</div>
</div>
</body>
</html>"""


def _approval_result_html(result: Dict[str, Any], decision: str) -> str:
    """Render the approval result page."""
    status = result.get("status", "ok")
    terminal = result.get("terminal", {})
    terminal_type = terminal.get("type", "unknown")
    is_approved = decision == "approve"
    human_comment = result.get("human_comment", "")

    if is_approved:
        title = "Action Approved"
        message = f"The action has been approved and published. Terminal: {terminal_type}"
        color = "var(--ok)"
    else:
        title = "Action Rejected"
        message = "The action has been rejected and an escalation has been recorded."
        color = "var(--danger)"

    comment_html = ""
    if human_comment:
        comment_html = f'<div class="comment-box"><strong>Reviewer Comment:</strong><br>{_esc(human_comment)}</div>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ForgeMind · {"Approved" if is_approved else "Rejected"}</title>
<style>
:root {{ color-scheme: dark; --bg:#09090b; --surface:#111113; --border:#27272a;
  --text:#fafafa; --text-2:#a1a1aa; --ok:#34d399; --danger:#f87171; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font:15px/1.55 ui-sans-serif,system-ui,sans-serif; }}
.wrap {{ max-width:600px; margin:0 auto; padding:2rem 1.5rem; }}
.card {{ background:var(--surface); border:1px solid var(--border);
  border-radius:10px; padding:1.5rem; }}
h1 {{ margin:0 0 .5rem; color:{color}; }}
p {{ color:var(--text-2); margin:0; }}
.comment-box {{ margin-top:1rem; padding:.8rem; background:rgba(96,165,250,.08);
  border:1px solid rgba(96,165,250,.3); border-radius:8px; font-size:.85rem; color:var(--text-2); }}
</style>
</head>
<body>
<div class="wrap">
<div class="card">
<h1>{title}</h1>
<p>{message}</p>
{comment_html}
</div>
</div>
</body>
</html>"""
from forgemind.api.errors import PIPELINE_ERRORS, SERVICE_VERSION
from forgemind.api.models import ApprovalDecision, EventInput
from forgemind.api.pipeline import _fixture_body_for, run_pipeline
from forgemind.situation_store import SituationStore

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
    """Build the ForgeMind FastAPI application (uvicorn ``--factory`` target).

    Loads the gitignored project-root ``.env`` before routes are registered
    (local-dev convenience so ``GITHUB_TOKEN`` etc. need no shell export);
    a no-op under pytest and in production images (no ``.env`` present).
    """
    load_dotenv()
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

    @app.get("/api/v1/approvals/{token}")
    async def approval_view(token: str, decision: Optional[str] = None, comment: str = ""):
        """View or act on a pending approval.

        Without ``decision``: returns an HTML approval page with comment field.
        With ``decision=approve|reject``: processes the decision and returns result.
        """
        if not is_adk_runtime():
            return JSONResponse(
                status_code=404,
                content={
                    "error": "not_found",
                    "detail": "human-approval resume is only available when FORGEMIND_RUNTIME=adk",
                },
            )

        if decision is None:
            # Return approval page with comment field
            return HTMLResponse(content=_approval_page_html(token))

        # Process decision from query param
        try:
            result = resume_adk_pipeline(token, decision, user_comment=comment)
            return HTMLResponse(content=_approval_result_html(result, decision))
        except ApprovalError as exc:
            return HTMLResponse(
                content=f"<!DOCTYPE html><html><body><h1>Approval Error</h1><p>{_esc(str(exc))}</p></body></html>",
                status_code=404,
            )

    @app.post("/api/v1/approvals/{token}")
    async def approve(token: str, decision: ApprovalDecision):
        """Human-approval resume endpoint for the ADK M3-B pause gate."""
        if not is_adk_runtime():
            return JSONResponse(
                status_code=404,
                content={
                    "error": "not_found",
                    "detail": "human-approval resume is only available when FORGEMIND_RUNTIME=adk",
                },
            )
        try:
            return resume_adk_pipeline(token, decision.decision)
        except ApprovalError as exc:
            return JSONResponse(
                status_code=404,
                content={"error": "not_found", "detail": str(exc)},
            )

    @app.post("/api/v1/approvals/{token}/form")
    async def approve_form(token: str, request: Request):
        """Handle form-encoded approval submission (from the approval page)."""
        if not is_adk_runtime():
            return HTMLResponse(
                content="<!DOCTYPE html><html><body><h1>Not Available</h1>"
                        "<p>human-approval resume is only available when "
                        "FORGEMIND_RUNTIME=adk</p></body></html>",
                status_code=404,
            )
        form = await request.form()
        decision_val = str(form.get("decision", ""))
        comment_val = str(form.get("comment", ""))
        try:
            result = resume_adk_pipeline(token, decision_val, user_comment=comment_val)
            return HTMLResponse(content=_approval_result_html(result, decision_val))
        except ApprovalError as exc:
            return HTMLResponse(
                content=f"<!DOCTYPE html><html><body><h1>Approval Error</h1>"
                        f"<p>{_esc(str(exc))}</p></body></html>",
                status_code=404,
            )

    # Register ADK 2.0 integration routes under /api/v1/adk/.
    # Idempotent and safe when google-adk is not installed.
    register_adk_routes(app)

    return app


#: Module-level ASGI app (convenience alternative to ``--factory`` usage).
app = create_api()
