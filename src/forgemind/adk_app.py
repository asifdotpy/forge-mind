"""ADK 2.0 Runner entry point for ForgeMind.

This module realises the real Google ADK 2.0 integration: it builds an ADK
:class:`~google.adk.Runter` wired with a root agent, sub-agents (Supervisor,
Domain Managers, Specialist Workers, Validator, Reducer, Action Gate), a
session service, and a memory service.

The module imports google.adk lazily so that ``import forgemind.adk_app``
succeeds on machines without ``google-adk`` installed (ADR-009 invariant).
All ADK imports live inside :func:`create_adk_runner` and the route handlers.

Activation: the ADK runner is only constructed when ``FORGEMIND_RUNTIME=adk``
and ``google-adk`` is importable.  The deterministic pipeline is byte-for-byte
unaffected otherwise.

ROLE NOTE: the authoritative decision-execution graph is the hierarchical DAG
in :func:`forgemind.adk_runtime.run_adk_pipeline` (Supervisor -> Managers ->
Workers -> Validator -> Reducer -> Action Gate, with the pause/resume human
gate).  The ``google.adk.Runner`` built here hosts the ``root_agent`` as a
discovery / session-memory surface (``GET /api/v1/adk/agents``,
``GET /api/v1/adk/sessions/...``); it is NOT used to execute decisions.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Sentinel objects returned when google-adk is not importable.
_ADK_UNAVAILABLE = object()


def _import_adk() -> Any:
    """Import google.adk, returning a sentinel on failure (never raises).

    Lazy import keeps the ADR-009 import-boundary test green: the package
    boots cleanly offline / without google-adk installed.
    """
    try:
        import google.adk  # noqa: F401
        return google.adk
    except ImportError:
        logger.debug("google-adk not importable; ADK runner unavailable")
        return _ADK_UNAVAILABLE


def is_adk_available() -> bool:
    """True only when the ``google-adk`` package is importable."""
    return _import_adk() is not _ADK_UNAVAILABLE


def create_adk_runner(
    *,
    app_name: str = "forgemind",
    session_service: Optional[Any] = None,
    memory_service: Optional[Any] = None,
) -> Any:
    """Build and return the ADK 2.0 Runner wired with the ForgeMind root agent.

    The Runner is the ADK entry point: it owns the agent graph, the session
    service (state between turns), and the memory service (long-term recall).
    It is constructed lazily and only when ``google-adk`` is importable.

    Args:
        app_name: Logical name for the ADK application (used in session keys).
        session_service: Optional override for the ADK session service.
            Defaults to :class:`~google.adk.sessions.InMemorySessionService`.
        memory_service: Optional override for the ADK memory service.
            Defaults to :class:`~google.adk.memory.VertexAiMemoryBankService`
            when Vertex credentials are configured; otherwise an in-memory
            fallback so the runner is always functional.

    Returns:
        An instantiated ``google.adk.Runner`` or ``None`` when
        ``google-adk`` is not importable.

    Raises:
        RuntimeError: If ADK is importable but the Runner cannot be built
            (misconfiguration, missing credentials for VertexAiMemoryBank
            when explicitly requested, etc.).
    """
    adk = _import_adk()
    if adk is _ADK_UNAVAILABLE:
        logger.info(
            "google-adk not installed; create_adk_runner() returning None. "
            "Install with `uv pip install google-adk>=2.0.0` to enable the "
            "FORGEMIND_RUNTIME=adk path."
        )
        return None

    # Lazy imports — only reached when google-adk IS importable.
    from google.adk.agents import SequentialAgent  # type: ignore[import-untyped]
    from google.adk.memory import InMemoryMemoryService  # type: ignore[import-untyped]
    from google.adk.sessions import InMemorySessionService  # type: ignore[import-untyped]

    from forgemind.agents.root_agent import build_root_agent

    # -- Session service ------------------------------------------------
    # InMemorySessionService is the default: stateless across restarts,
    # matching ForgeMind's existing deterministic model.  Callers may
    # substitute a persistent implementation (e.g. Cloud SQL-backed) via
    # the session_service kwarg.
    _session_service = session_service or InMemorySessionService()

    # -- Memory service ------------------------------------------------
    # VertexAiMemoryBankService is the production choice when running on
    # GCP with Vertex credentials.  Without credentials (local dev, CI, or
    # non-GCP deployments) we fall back to InMemoryMemoryService so the
    # runner is always constructible.
    if memory_service is not None:
        _memory_service = memory_service
    else:
        _memory_service = _try_vertex_memory() or InMemoryMemoryService()

    # -- Root agent ----------------------------------------------------
    # The root agent wires together the Supervisor, Domain Managers, Workers,
    # Validator, Reducer, and Action Gate as an ADK SequentialAgent graph.
    root_agent = build_root_agent()

    # -- Runner --------------------------------------------------------
    runner = adk.Runner(
        app_name=app_name,
        agent=root_agent,
        session_service=_session_service,
        memory_service=_memory_service,
    )

    logger.info(
        "ADK runner created (app_name=%s, session=%s, memory=%s)",
        app_name,
        type(_session_service).__name__,
        type(_memory_service).__name__,
    )
    return runner


def create_adk_tool_runner(
    *,
    app_name: str = "forgemind",
    session_service: Optional[Any] = None,
    memory_service: Optional[Any] = None,
) -> Any:
    """Build and return the ADK 2.0 Runner wired with the tool-driven root agent.

    This Runner executes the 5-tier DAG through tool calls that read/write
    tool_context.state for the ``FORGEMIND_RUNTIME=adk+runner`` runtime.
    """
    adk = _import_adk()
    if adk is _ADK_UNAVAILABLE:
        logger.info(
            "google-adk not installed; create_adk_tool_runner() returning None."
        )
        return None

    from google.adk.memory import InMemoryMemoryService  # type: ignore[import-untyped]
    from google.adk.sessions import InMemorySessionService  # type: ignore[import-untyped]

    from forgemind.agents.root_agent import build_runner_root_agent

    _session_service = session_service or InMemorySessionService()
    if memory_service is not None:
        _memory_service = memory_service
    else:
        _memory_service = _try_vertex_memory() or InMemoryMemoryService()

    root_agent = build_runner_root_agent()

    runner = adk.Runner(
        app_name=app_name,
        agent=root_agent,
        session_service=_session_service,
        memory_service=_memory_service,
    )

    logger.info(
        "ADK tool runner created (app_name=%s, session=%s, memory=%s)",
        app_name,
        type(_session_service).__name__,
        type(_memory_service).__name__,
    )
    return runner


# -- Per-tier ADK agent builders (kept here so the root agent composes them) --

def build_supervisor_agent() -> Any:
    """Build the ADK LlmAgent wrapper around the existing Supervisor tier.

    The Supervisor is the single entry point of the five-tier DAG.  As an ADK
    agent it acquires the Event, produces a CoveragePlan, and dispatches to
    the selected Domain Managers.
    """
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]

    from forgemind.supervisor import Supervisor

    return LlmAgent(
        name="supervisor",
        description=(
            "Tier 1 Supervisor: acquires an Event, produces a CoveragePlan, "
            "and dispatches to the selected Domain Managers."
        ),
        model=_adk_model(),
        # The agent's behavior is delegated to the deterministic Supervisor;
        # the LlmAgent wrapper exposes it to the ADK Runner.
        instruction=(
            "You are the Tier 1 Supervisor. Acquire the event, build the "
            "CoveragePlan, and dispatch to the appropriate domain managers. "
            "Ground all outputs in the event payload."
        ),
    )


def build_worker_agent() -> Any:
    """Build the ADK LlmAgent wrapper around the Specialist Workers tier."""
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]

    return LlmAgent(
        name="workers",
        description=(
            "Tier 2 Specialist Workers: produce EvidenceShards for each "
            "selected domain from the CoveragePlan."
        ),
        model=_adk_model(),
        instruction=(
            "You are the Specialist Workers. Produce grounded EvidenceShards "
            "for each domain selected in the CoveragePlan. "
            "Stay inside the domain boundary; never invent cross-domain facts."
        ),
    )


def build_manager_agent() -> Any:
    """Build the ADK LlmAgent wrapper around the Domain Managers tier."""
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]

    return LlmAgent(
        name="managers",
        description=(
            "Tier 3 Domain Managers: aggregate EvidenceShards into "
            "per-domain DomainFindings."
        ),
        model=_adk_model(),
        instruction=(
            "You are the Domain Managers. Aggregate the supplied "
            "EvidenceShards into a single DomainFinding per domain."
        ),
    )


def build_validator_agent() -> Any:
    """Build the ADK LlmAgent wrapper around the Cross-Lifecycle Validator."""
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]

    return LlmAgent(
        name="validator",
        description=(
            "Tier 4 Cross-Lifecycle Validator: reconcile all DomainFindings "
            "into the single authoritative ValidatedSituation."
        ),
        model=_adk_model(),
        instruction=(
            "You are the Cross-Lifecycle Validator. Reconcile all "
            "DomainFindings into one ValidatedSituation. "
            "You are the ONLY tier authorised to reconcile across domains."
        ),
    )


def build_reducer_agent() -> Any:
    """Build the ADK LlmAgent wrapper around the Decision Reducer."""
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]

    return LlmAgent(
        name="reducer",
        description=(
            "Tier 5 Decision Reducer: convert the ValidatedSituation into "
            "an operational decision (autonomous action or escalation) via "
            "the autonomy confidence ladder."
        ),
        model=_adk_model(),
        instruction=(
            "You are the Decision Reducer. Produce a DecisionRecord and "
            "either a ProposedAction or an Escalation. Apply the autonomy "
            "ladder strictly; never escalate what the ladder permits."
        ),
    )


def build_action_gate_agent() -> Any:
    """Build the ADK LlmAgent wrapper around the Action Validation Gate."""
    from google.adk.agents import LlmAgent  # type: ignore[import-untyped]

    return LlmAgent(
        name="action_gate",
        description=(
            "Action Validation Gate: the structural no-bypass point. Every "
            "terminal Action or Escalation must flow through here."
        ),
        model=_adk_model(),
        instruction=(
            "You are the Action Validation Gate. Validate the ProposedAction "
            "against policy. Either approve (publish) or escalate. "
            "This gate cannot be bypassed."
        ),
    )


# -- Helpers ----------------------------------------------------------

def _adk_model() -> Any:
    """Resolve the ADK model.
    
    Returns a Gemini instance with a pre-configured client using API key mode
    when GOOGLE_API_KEY is present, or returns the model name / default Gemini.
    """
    model_name = os.environ.get("FORGEMIND_ADK_MODEL", "gemini-3.5-flash")
    try:
        from google.adk.models.google_llm import Gemini
        from google import genai

        api_key = os.environ.get("GOOGLE_API_KEY")
        if api_key:
            client = genai.Client(api_key=api_key)
            return Gemini(model=model_name, client=client)
        # Fallback to model string if no explicit API key is configured
        return model_name
    except Exception:
        return model_name


def _try_vertex_memory() -> Optional[Any]:
    """Return a VertexAiMemoryBankService if credentials are configured.

    Returns ``None`` when Vertex is not configured so callers can fall back
    to an in-memory implementation.
    """
    try:
        from google.adk.memory import VertexAiMemoryBankService  # type: ignore[import-untyped]
    except ImportError:
        logger.debug(
            "VertexAiMemoryBankService not importable; "
            "using InMemoryMemoryService fallback."
        )
        return None

    project = os.environ.get("VERTEX_PROJECT") or os.environ.get(
        "GOOGLE_CLOUD_PROJECT"
    )
    if not project:
        logger.debug(
            "No Vertex project configured (VERTEX_PROJECT / "
            "GOOGLE_CLOUD_PROJECT unset); using InMemoryMemoryService fallback."
        )
        return None

    location = (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("VERTEX_LOCATION")
        or "global"
    )
    agent_builder_project = os.environ.get("FORGEMIND_VERTEX_AGENT_BUILDER_PROJECT", project)

    try:
        service = VertexAiMemoryBankService(
            project=agent_builder_project,
            location=location,
        )
        logger.info(
            "VertexAiMemoryBankService initialised "
            "(project=%s, location=%s)",
            agent_builder_project,
            location,
        )
        return service
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "VertexAiMemoryBankService init failed (%s); "
            "falling back to InMemoryMemoryService.",
            exc,
        )
        return None


def describe_adk_agents() -> Dict[str, str]:
    """Return a name -> description map of every registered ADK agent.

    Used by the ``GET /api/v1/adk/agents`` discovery endpoint.  Safe to call
    when google-adk is unavailable (returns a descriptive placeholder).
    """
    if not is_adk_available():
        return {
            "_unavailable": (
                "google-adk is not installed. Install with "
                "`uv pip install google-adk>=2.0.0`."
            )
        }
    return {
        "supervisor": "Tier 1: Event acquisition + CoveragePlan dispatch",
        "workers": "Tier 2: Specialist Workers producing EvidenceShards",
        "managers": "Tier 3: Domain Managers aggregating findings",
        "validator": "Tier 4: Cross-Lifecycle Validator reconciling findings",
        "reducer": "Tier 5: Decision Reducer applying the autonomy ladder",
        "action_gate": "Action Validation Gate (structural no-bypass point)",
    }