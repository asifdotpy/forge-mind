"""ForgeMind HTTP API layer (SPEC-001 M2 — Cloud Run deployment prep).

Thin FastAPI wrapper over the completed five-tier runtime DAG.  This module
adds ZERO business logic: every request drives the exact pipeline already
exercised by ``scripts/run_fixture.py``, step for step::

    Acquire -> Supervisor -> Workers -> Managers -> Validator
            -> Reducer -> ActionValidationGate -> publish_terminal_output

Endpoints (all under ``/api/v1``):

===============  =======================  ==================================
Method           Path                     Purpose
===============  =======================  ==================================
GET              /api/v1/health           Liveness probe for Cloud Run
POST             /api/v1/events           Run an Event through the pipeline
GET              /api/v1/specs            List canonical JSON Schema contracts
GET              /api/v1/specs/{name}     Fetch one contract schema
GET              /api/v1/situations/{id}  Re-derive a situation + M3 proof
GET              / and /view/{id}         Read-only HTML judge-visible viewer
===============  =======================  ==================================

The ``POST /api/v1/events`` request envelope mirrors the canonical fixture
layout, so any ``fixtures/inputs/*.json`` file can be posted verbatim::

    {
      "event": {...},             # required; validated by acquire_event()
      "workers": {...},           # optional Tier 3 per-worker contexts
      "evidence_shards": [...],   # optional pre-computed EvidenceShards
      "domain_findings": [...]    # optional pre-computed DomainFindings
    }

Unknown envelope keys are ignored (fixtures carry fixture_id / name /
purpose / expected_artifacts alongside the event).

Error mapping:

=============================  ========  ====================================
Condition                      Status    Body
=============================  ========  ====================================
Event rejected by acquisition   422      {"error": "validation_error", ...}
Tier raised its ``*Error``      500      {"error": "pipeline_error", ...}
Unknown contract name           404      {"error": "not_found", ...}
=============================  ========  ====================================

Run locally::

    uvicorn forgemind.api:create_api --factory --reload
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict

from forgemind._paths import CONTRACTS_DIR, FIXTURES_INPUT_DIR
from forgemind.m3_proof import build_m3_proof
from forgemind.acquisition import EventValidationError, acquire_event
from forgemind.action_gate import (
    ActionGateError,
    ActionValidationGate,
    publish_terminal_output,
)
from forgemind.domain_managers import DomainManagerError, ManagerCoordinator
from forgemind.reducer import DecisionReducer, ReducerError
from forgemind.supervisor import Supervisor, SupervisorError
from forgemind.validator import CrossLifecycleValidator, ValidatorError
from forgemind.workers import WorkerCoordinator, WorkerError
from forgemind.adk_runtime import (
    ApprovalError,
    is_adk_runtime,
    resume_adk_pipeline,
    run_adk_pipeline,
)

logger = logging.getLogger(__name__)

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


class EventInput(BaseModel):
    """Request envelope for ``POST /api/v1/events``.

    Only ``event`` is required.  The Event dict itself is deliberately NOT
    re-modelled field-by-field: conformance to
    ``contracts/event.schema.json`` is enforced by
    :func:`forgemind.acquire_event` (the single source of truth), and a
    rejection surfaces as HTTP 422.
    """

    model_config = ConfigDict(extra="ignore")

    #: Canonical Event object (SPEC-001 contract).
    event: Dict[str, Any]
    #: Optional Tier 3 per-worker context mapping (the fixture ``workers`` key).
    workers: Optional[Dict[str, Any]] = None
    #: Optional durable EvidenceShards fed to Tier 2 aggregation.
    evidence_shards: Optional[List[Dict[str, Any]]] = None
    #: Optional DomainFindings handed directly to the Tier 4 validator.
    domain_findings: Optional[List[Dict[str, Any]]] = None


class ApprovalDecision(BaseModel):
    """Request body for ``POST /api/v1/approvals/{token}`` (ADK M3-B)."""

    model_config = ConfigDict(extra="ignore")

    #: Human decision on a PAUSED workflow: approve (publish) or reject.
    decision: Literal["approve", "reject"]


def run_pipeline(body: EventInput) -> Dict[str, Any]:
    """Drive one Event through the five-tier DAG and assemble the response.

    Pure orchestration of existing tiers — no new logic.  Raises the tiers'
    own error classes (:class:`EventValidationError`, :data:`PIPELINE_ERRORS`);
    HTTP mapping happens in the route handler.
    """
    # Acquire layer: normalize + validate against event.schema.json,
    # derive execution_trace_id / coverage_plan_id deterministically.
    acquired = acquire_event(body.event)
    event = acquired["event"]
    plan = acquired["coverage_plan"]

    # Tier 1 — Engineering Supervisor: constraint enforcement + dispatch trace.
    supervisor_dispatch = Supervisor().dispatch(plan)

    # Tier 3 — Specialist Workers (optional): emit durable EvidenceShards.
    shards: List[Dict[str, Any]] = list(body.evidence_shards or [])
    if body.workers:
        worker_outcome = WorkerCoordinator().dispatch(plan, body.workers)
        shards.extend(worker_outcome["shards"])

    # Tier 2 — Domain Managers: aggregate shards into bounded DomainFindings.
    findings_by_domain: Dict[str, Dict[str, Any]] = {}
    if shards:
        manager_outcome = ManagerCoordinator().dispatch(
            supervisor_dispatch, plan, shards
        )
        findings_by_domain = manager_outcome["findings"]

    # Tier 4 — Cross-Lifecycle Validator.  ALWAYS reconciles: an empty finding
    # set is the honest zero-confidence, coverage-gapped picture and MUST
    # escalate downstream (never act) — mirroring the FIXTURE-002 semantics.
    if body.domain_findings is not None:
        domain_findings = list(body.domain_findings)
    else:
        domain_findings = [
            findings_by_domain[domain] for domain in sorted(findings_by_domain)
        ]
    validated = CrossLifecycleValidator().validate(
        plan, domain_findings, shards or None
    )

    # Tier 5 — Decision Reducer: deterministic autonomy ladder.
    reduction = DecisionReducer().reduce(validated)
    decision_record = reduction["decision_record"]

    if reduction["proposed_action"] is not None:
        # Downstream safety gate, then the structural no-bypass publish point.
        gated = ActionValidationGate().validate(
            reduction["proposed_action"],
            decision_record,
            event_timestamp=event["timestamp"],
        )
        published = publish_terminal_output(
            gated["proposed_action"],
            gated["action_validation"],
            situation_id=plan["situation_id"],
            evidence_ids=validated.get("evidence_ids") or [],
        )
        terminal: Dict[str, Any] = {
            "type": published["terminal"],
            "decision_record": decision_record,
            "proposed_action": published["action"],
            "action_validation": gated["action_validation"],
            "escalation": published["escalation"],
        }
    else:
        # A reducer-produced Escalation is already terminal (human required);
        # publish_terminal_output only accepts gated ProposedActions.
        terminal = {
            "type": "escalation",
            "decision_record": decision_record,
            "proposed_action": None,
            "action_validation": None,
            "escalation": reduction["escalation"],
        }

    result: Dict[str, Any] = {
        "status": "ok",
        "situation_id": plan["situation_id"],
        "trace_id": plan["execution_trace_id"],
        "terminal": terminal,
        "artifacts": {
            "coverage_plan": plan,
            "supervisor_dispatch": supervisor_dispatch,
            "evidence_shards": shards,
            "domain_findings": domain_findings,
            "validated_situation": validated,
        },
    }
    # M3-A (T720): additive, presentation-only projection of the result into
    # the four judge-visible properties.  No tier logic is involved.
    result["m3_proof"] = build_m3_proof(result)
    return result


def _fixture_body_for(situation_id: str) -> Optional[EventInput]:
    """Find a repository fixture whose Event carries ``situation_id``.

    The runtime is stateless (no artifact store), so ``GET
    /api/v1/situations/{id}`` re-derives the situation by replaying the
    matching canonical fixture input.  Returns ``None`` when nothing matches.
    """
    for path in sorted(FIXTURES_INPUT_DIR.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):  # pragma: no cover - corrupt fixture
            continue
        event = payload.get("event")
        if isinstance(event, dict) and event.get("situation_id") == situation_id:
            return EventInput(**payload)
    return None


#: Default fixture situation rendered by the read-only viewer (M3-A / T721).
DEFAULT_VIEWER_SITUATION_ID = "SIT-1000"

#: Inline stylesheet — no CDN, no JS framework; the viewer works fully offline.
_VIEWER_CSS = """
:root { color-scheme: light; }
body { font-family: ui-sans-serif, system-ui, "Segoe UI", Arial, sans-serif;
       margin: 0; padding: 2rem; background: #f6f7f9; color: #16181d; }
h1 { font-size: 1.35rem; margin: 0 0 .25rem; }
h2 { font-size: .95rem; letter-spacing: .06em; text-transform: uppercase;
     color: #55606e; margin: 0 0 .75rem; }
.sub { color: #55606e; font-size: .85rem; margin: 0 0 1.5rem; }
section { background: #fff; border: 1px solid #dfe3e8; border-radius: 10px;
          padding: 1.1rem 1.25rem; margin-bottom: 1.25rem; }
.flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: .35rem; }
.node { border: 1px solid #cfd6de; border-radius: 8px; background: #fbfcfd;
        padding: .5rem .65rem; min-width: 8.5rem; }
.node .a { font-weight: 600; font-size: .8rem; }
.node .i { font-family: ui-monospace, Consolas, monospace; font-size: .72rem;
           color: #1d4ed8; word-break: break-all; }
.node .u { font-size: .68rem; color: #6b7480; }
.arrow { align-self: center; color: #98a2b3; font-size: 1.1rem; }
.pill { display: inline-block; border-radius: 999px; padding: .2rem .7rem;
        font-size: .78rem; font-weight: 700; color: #fff; }
.pill.green { background: #157f3d; }
.pill.amber { background: #b06f00; }
.pill.red { background: #b3261e; }
.banner { border-left: 5px solid #98a2b3; padding: .6rem .9rem;
          background: #f2f4f7; border-radius: 6px; }
.banner.green { border-color: #157f3d; }
.banner.amber { border-color: #b06f00; }
.banner.red { border-color: #b3261e; }
dl { display: grid; grid-template-columns: 12rem 1fr; gap: .3rem .8rem;
     margin: 0; font-size: .85rem; }
dt { color: #55606e; }
dd { margin: 0; font-family: ui-monospace, Consolas, monospace; }
ul { margin: .5rem 0 0; padding-left: 1.2rem; font-size: .85rem; }
.none { color: #6b7480; font-style: italic; }
"""

#: verdict / control state -> badge colour class.
_STATE_COLOR = {
    "automated": "green",
    "human_review": "amber",
    "human_review_required": "amber",
    "escalated": "red",
}


def _esc(value: Any) -> str:
    """Minimal HTML escaping for untrusted artifact values."""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _fmt(value: Any) -> str:
    if value is None or value == [] or value == "":
        return '<span class="none">none</span>'
    if isinstance(value, (list, tuple)):
        return _esc(", ".join(str(v) for v in value))
    return _esc(value)


def _render_situation_html(result: Dict[str, Any]) -> str:
    """Render the read-only M3 situation viewer (T721).

    Reads ONLY ``build_m3_proof`` output plus the situation/trace ids — no tier
    logic is re-implemented here.
    """
    proof = result.get("m3_proof") or build_m3_proof(result)
    links = proof["provenance_links"]
    verdict = proof["validation_verdict"]
    uncertainty = proof["uncertainty_summary"]
    control = proof["human_control_state"]

    nodes = [f'<div class="node"><div class="a">Event</div>'
             f'<div class="i">{_esc(links["event_id"])}</div>'
             f'<div class="u">origin</div></div>']
    for entry in links["artifact_chain"]:
        nodes.append(
            '<div class="node">'
            f'<div class="a">{_esc(entry["artifact"])}</div>'
            f'<div class="i">{_fmt(entry["id"])}</div>'
            f'<div class="u">&larr; {_esc(", ".join(entry["upstream"]))}</div>'
            "</div>"
        )
    flow = '<span class="arrow">&rarr;</span>'.join(nodes)

    uncertainties = uncertainty["uncertainties"]
    if uncertainties:
        items = "".join(f"<li>{_esc(u)}</li>" for u in uncertainties)
        uncertainty_list = f"<ul>{items}</ul>"
    else:
        uncertainty_list = '<p class="none">no uncertainties recorded</p>'

    verdict_color = _STATE_COLOR.get(verdict["state"], "amber")
    control_color = _STATE_COLOR.get(control["state"], "amber")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ForgeMind situation {_esc(links['situation_id'])}</title>
<style>{_VIEWER_CSS}</style></head>
<body>
<h1>ForgeMind judge-visible surface</h1>
<p class="sub">situation <strong>{_esc(links['situation_id'])}</strong>
&middot; execution trace <strong>{_esc(links['execution_trace_id'])}</strong>
&middot; terminal <strong>{_esc((result.get('terminal') or {}).get('type'))}</strong>
&middot; read-only, offline</p>

<section>
  <h2>1. Provenance lineage</h2>
  <div class="flow">{flow}</div>
  <dl style="margin-top:1rem">
    <dt>event_id</dt><dd>{_fmt(links['event_id'])}</dd>
    <dt>coverage_plan_id</dt><dd>{_fmt(links['coverage_plan_id'])}</dd>
    <dt>execution_trace_id</dt><dd>{_fmt(links['execution_trace_id'])}</dd>
    <dt>situation_id</dt><dd>{_fmt(links['situation_id'])}</dd>
  </dl>
</section>

<section>
  <h2>2. Validation verdict</h2>
  <p><span class="pill {verdict_color}">{_esc(verdict['state'])}</span></p>
  <dl>
    <dt>policy_result</dt><dd>{_fmt(verdict['policy_result'])}</dd>
    <dt>reason</dt><dd>{_fmt(verdict['reason'])}</dd>
    <dt>validation_id</dt><dd>{_fmt(verdict['validation_id'])}</dd>
  </dl>
</section>

<section>
  <h2>3. Uncertainty callouts</h2>
  <dl>
    <dt>causality_status</dt><dd>{_fmt(uncertainty['causality_status'])}</dd>
    <dt>confidence</dt><dd>{_fmt(uncertainty['confidence'])}</dd>
    <dt>coverage_percentage</dt><dd>{_fmt(uncertainty['coverage_percentage'])}</dd>
    <dt>missing_domains</dt><dd>{_fmt(uncertainty['missing_domains'])}</dd>
  </dl>
  {uncertainty_list}
</section>

<section>
  <h2>4. Human control</h2>
  <div class="banner {control_color}">
    <strong>{_esc(control['state'])}</strong> &mdash;
    autonomy_class {_fmt(control['autonomy_class'])},
    risk_level {_fmt(control['risk_level'])},
    required_human_role {_fmt(control['required_human_role'])}
  </div>
</section>
<footer class="sub">M3 proof blocks rendered: provenance, validation, uncertainty,
human control &mdash; derived from build_m3_proof(), no external assets.</footer>
</body></html>
"""


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

    return app


#: Module-level ASGI app (convenience alternative to ``--factory`` usage).
app = create_api()
