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
from typing import Any, Dict, List, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from forgemind._paths import CONTRACTS_DIR
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

    return {
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

    return app


#: Module-level ASGI app (convenience alternative to ``--factory`` usage).
app = create_api()
