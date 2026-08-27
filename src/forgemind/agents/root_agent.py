"""Root ADK agent composition for ForgeMind.

Builds the top-level SequentialAgent that wires the five-tier DAG
(Supervisor -> Workers -> Managers -> Validator -> Reducer -> Action Gate)
into a single ADK agent graph.

The root agent is constructed lazily; all ADK imports are deferred until
call time so the module imports cleanly without google-adk installed.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


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