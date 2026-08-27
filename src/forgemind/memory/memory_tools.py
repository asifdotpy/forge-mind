"""Memory tools for ForgeMind ADK agents.

Tools that agents can call to interact with long-term memory.
All tools fail gracefully when Memory Bank is not configured.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def remember_pattern(pattern: str, context: str) -> Dict[str, Any]:
    """Store a pattern in long-term memory.

    Args:
        pattern: The pattern to remember.
        context: Additional context about the pattern.

    Returns:
        Dict with success status.
    """
    try:
        from forgemind.memory.memory_service import add_memory
        success = add_memory(
            app_name="forgemind",
            user_id="system",
            memory_text=f"Pattern: {pattern}\nContext: {context}",
        )
        return {"success": success, "message": "Pattern stored" if success else "Memory unavailable"}
    except Exception as exc:
        logger.warning("remember_pattern failed: %s", exc)
        return {"success": False, "error": str(exc)}


def recall_similar_situations(query: str) -> List[str]:
    """Recall similar situations from long-term memory.

    Args:
        query: Search query for finding similar situations.

    Returns:
        List of matching memory texts. Empty list if unavailable.
    """
    try:
        from forgemind.memory.memory_service import search_memory
        return search_memory(
            app_name="forgemind",
            user_id="system",
            query=query,
        )
    except Exception as exc:
        logger.warning("recall_similar_situations failed: %s", exc)
        return []


def get_agent_history(agent_name: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Get recent history for an agent.

    Args:
        agent_name: Name of the agent.
        limit: Maximum number of history entries to return.

    Returns:
        List of history entries. Empty list if unavailable.
    """
    # History is stored in session state, not Memory Bank
    return []
