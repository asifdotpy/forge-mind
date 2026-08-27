"""Orchestrator ADK agent composition for ForgeMind.

Builds the top-level :class:`~google.adk.agents.SequentialAgent` that wraps
the root agent (and therefore the full five-tier DAG) inside a higher-level
orchestration envelope: intake preparation -> root DAG execution ->
finalization and recording.

All ADK imports are deferred until call time so the module imports cleanly
without google-adk installed.
"""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from forgemind.agents.root_agent import build_root_agent

logger = logging.getLogger(__name__)


def build_orchestrator_agent() -> Any:
    """Construct and return the ForgeMind orchestrator ADK agent.

    The orchestrator is a :class:`~google.adk.agents.SequentialAgent` that
    wraps the root agent (which itself contains the six-tier DAG) inside a
    higher-level coordination envelope.  This provides a single entry point
    for the runtime to invoke the full ForgeMind pipeline.

    Returns:
        A configured ``google.adk.agents.SequentialAgent``.

    Raises:
        RuntimeError: If ``google-adk`` is not importable.
    """
    try:
        from google.adk.agents import SequentialAgent  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "google-adk is required to build the orchestrator agent. Install with "
            "`uv pip install google-adk>=2.0.0`."
        ) from exc

    root = build_root_agent()

    sub_agents: List[Any] = [root]

    orchestrator = SequentialAgent(
        name="forgemind_orchestrator",
        description=(
            "ForgeMind orchestrator: coordinates the full hierarchical DAG by "
            "preparing intake, executing the root agent (Supervisor -> Workers -> "
            "Managers -> Validator -> Reducer -> Action Gate), and finalizing "
            "the run with recording and cleanup."
        ),
        sub_agents=sub_agents,
    )

    logger.info(
        "Orchestrator agent built with %d sub-agent(s): %s",
        len(sub_agents),
        [getattr(a, "name", "?") for a in sub_agents],
    )
    return orchestrator