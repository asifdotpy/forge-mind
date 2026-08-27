from __future__ import annotations

"""Pydantic request envelopes for the ForgeMind HTTP API."""
from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, ConfigDict

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
