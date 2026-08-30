"""Root ADK agent composition for ForgeMind.

Builds the top-level SequentialAgent that wires the five-tier DAG
(Supervisor -> Workers -> Managers -> Validator -> Reducer -> Action Gate)
into a single ADK agent graph.

NOTE ON ROLE (hierarchy): the authoritative decision-execution path in
ForgeMind is the hierarchical DAG in :func:`forgemind.adk_runtime.run_adk_pipeline`
— Acquire -> Supervisor (Tier 1) -> Domain Managers (Tier 2) -> Specialist
Workers (Tier 3) -> Validator (Tier 4) -> Reducer (Tier 5) -> Action Gate —
with parent->child delegation and the pause/resume human gate.  This module's
SequentialAgent is a Google ``google.adk`` discovery / coordination surface
(a ``Runner`` host for session-memory); it is NOT the execution graph and must
not be mistaken for one.  The tier ``LlmAgent`` wrappers below carry only
name/description/model/instruction and do no delegation logic.

The root agent is constructed lazily; all ADK imports are deferred until
call time so the module imports cleanly without google-adk installed.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


def build_runner_root_agent() -> Any:
    """Construct the tool-wired root agent for ``adk+runner`` mode.

    Each sub-agent is an :class:`~google.adk.agents.LlmAgent` with exactly
    one tool attached from :mod:`forgemind.tools.adk_tools`.  The agent's
    instruction forces it to call the tool exactly once (no reasoning loop,
    no multi-turn) — the LLM is the orchestration substrate, not the
    decision-maker.

    The tools read inputs from ``tool_context.state`` and write outputs
    back, so the ``SequentialAgent`` pipeline carries state forward through
    the ADK session without explicit hand-off code.

    Returns:
        A configured ``google.adk.agents.SequentialAgent`` with tool-wired
        sub-agents.

    Raises:
        RuntimeError: If ``google-adk`` is not importable.
    """
    try:
        from google.adk.agents import SequentialAgent, LlmAgent  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "google-adk is required to build the runner root agent. Install "
            "with `uv pip install google-adk>=2.0.0`."
        ) from exc

    from forgemind.adk_app import _adk_model
    from forgemind.tools.adk_tools import (
        call_supervisor,
        call_workers,
        call_managers,
        call_validator,
        call_reducer,
        call_action_gate,
    )

    # Each agent: one tool, one forced call, output_key for state writing.
    _FORCE = "Call the tool exactly once. Do not reason or ask questions."

    sub_agents = [
        LlmAgent(
            name="supervisor",
            description="Tier 1: Dispatch event through the Engineering Supervisor.",
            model=_adk_model(),
            instruction=f"You are the Tier 1 Supervisor agent. {_FORCE}",
            tools=[call_supervisor],
            output_key="supervisor_output",
        ),
        LlmAgent(
            name="workers",
            description="Tier 3: Run specialist workers to produce EvidenceShards.",
            model=_adk_model(),
            instruction=f"You are the Specialist Workers agent. {_FORCE}",
            tools=[call_workers],
            output_key="workers_output",
        ),
        LlmAgent(
            name="managers",
            description="Tier 2: Aggregate EvidenceShards into DomainFindings.",
            model=_adk_model(),
            instruction=f"You are the Domain Managers agent. {_FORCE}",
            tools=[call_managers],
            output_key="managers_output",
        ),
        LlmAgent(
            name="validator",
            description="Tier 4: Reconcile DomainFindings into ValidatedSituation.",
            model=_adk_model(),
            instruction=f"You are the Cross-Lifecycle Validator agent. {_FORCE}",
            tools=[call_validator],
            output_key="validator_output",
        ),
        LlmAgent(
            name="reducer",
            description="Tier 5: Reduce ValidatedSituation into a decision.",
            model=_adk_model(),
            instruction=f"You are the Decision Reducer agent. {_FORCE}",
            tools=[call_reducer],
            output_key="reducer_output",
        ),
        LlmAgent(
            name="action_gate",
            description="Action Validation Gate: structural no-bypass point.",
            model=_adk_model(),
            instruction=f"You are the Action Validation Gate agent. {_FORCE}",
            tools=[call_action_gate],
            output_key="gate_output",
        ),
    ]

    root = SequentialAgent(
        name="forgemind_runner_root",
        description=(
            "ForgeMind runner root agent: executes the five-tier DAG through "
            "tool calls that read/write session state."
        ),
        sub_agents=sub_agents,
    )

    logger.info(
        "Runner root agent built with %d tool-wired sub-agents: %s",
        len(sub_agents),
        [getattr(a, "name", "?") for a in sub_agents],
    )
    return root


def build_root_agent() -> Any:
    """Construct and return the ForgeMind root ADK agent.

    The root agent is a :class:`~google.adk.agents.SequentialAgent` that
    executes the five tiers in order.  Each tier is itself an ADK agent
    (LlmAgent wrapper around the deterministic tier logic).

    Returns:
        A configured ``google.adk.agents.SequentialAgent``.

    Raises:
        RuntimeError: If ``google-adk`` is not importable.
    """
    try:
        from google.adk.agents import SequentialAgent  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "google-adk is required to build the root agent. Install with "
            "`uv pip install google-adk>=2.0.0`."
        ) from exc

    from forgemind.adk_app import (
        build_supervisor_agent,
        build_worker_agent,
        build_manager_agent,
        build_validator_agent,
        build_reducer_agent,
        build_action_gate_agent,
    )

    sub_agents: List[Any] = [
        build_supervisor_agent(),
        build_worker_agent(),
        build_manager_agent(),
        build_validator_agent(),
        build_reducer_agent(),
        build_action_gate_agent(),
    ]

    root = SequentialAgent(
        name="forgemind_root",
        description=(
            "ForgeMind root agent: orchestrates the five-tier hierarchical "
            "DAG (Supervisor -> Workers -> Managers -> Validator -> Reducer "
            "-> Action Gate) over an incoming engineering event."
        ),
        sub_agents=sub_agents,
    )

    logger.info(
        "Root agent built with %d sub-agents: %s",
        len(sub_agents),
        [getattr(a, "name", "?") for a in sub_agents],
    )
    return root