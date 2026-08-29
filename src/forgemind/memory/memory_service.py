"""Memory Bank service wrapper for ForgeMind ADK agents.

Provides long-term memory capabilities using Vertex AI Memory Bank
(google.adk.memory). All operations fail gracefully when Memory Bank
is not configured — the module is importable offline and returns
empty results rather than raising.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_project() -> Optional[str]:
    """Read Vertex project from environment."""
    return os.environ.get("VERTEX_PROJECT") or os.environ.get("GOOGLE_CLOUD_PROJECT")


def _get_location() -> str:
    """Read Vertex location from environment."""
    return (
        os.environ.get("GOOGLE_CLOUD_LOCATION")
        or os.environ.get("VERTEX_LOCATION")
        or "global"
    )


def is_memory_available() -> bool:
    """Check if Vertex AI Memory Bank is available and configured."""
    if not _get_project():
        return False
    try:
        from google.adk.memory import VertexAiMemoryBankService  # type: ignore[import-untyped]
        return True
    except ImportError:
        return False


def create_memory_service() -> Optional[Any]:
    """Create a VertexAiMemoryBankService if possible.

    Returns None when Vertex is not configured or google-adk is not installed.
    """
    if not _get_project():
        logger.debug("No Vertex project configured; memory service unavailable")
        return None

    try:
        from google.adk.memory import VertexAiMemoryBankService  # type: ignore[import-untyped]
    except ImportError:
        logger.debug("google-adk not installed; memory service unavailable")
        return None

    try:
        service = VertexAiMemoryBankService(
            project=_get_project(),
            location=_get_location(),
        )
        logger.info(
            "VertexAiMemoryBankService initialised (project=%s, location=%s)",
            _get_project(),
            _get_location(),
        )
        return service
    except Exception as exc:
        logger.warning("VertexAiMemoryBankService init failed: %s", exc)
        return None


def add_memory(app_name: str, user_id: str, memory_text: str) -> bool:
    """Add a memory entry to the Memory Bank.

    Args:
        app_name: Logical application name.
        user_id: User identifier.
        memory_text: The memory content to store.

    Returns:
        True if the memory was added successfully, False otherwise.
    """
    service = create_memory_service()
    if service is None:
        return False

    try:
        import asyncio
        from google.adk.memory.memory_entry import MemoryEntry  # type: ignore[import-untyped]
        from google.genai.types import Content, Part  # type: ignore[import-untyped]

        async def _add():
            await service.add_memory(
                app_name=app_name,
                user_id=user_id,
                memories=[MemoryEntry(content=Content(parts=[Part(text=memory_text)]))],
            )

        asyncio.run(_add())
        return True
    except Exception as exc:
        logger.warning("add_memory failed: %s", exc)
        return False


def search_memory(app_name: str, user_id: str, query: str) -> List[str]:
    """Search the Memory Bank for relevant memories.

    Args:
        app_name: Logical application name.
        user_id: User identifier.
        query: Search query.

    Returns:
        List of matching memory texts. Empty list on failure.
    """
    service = create_memory_service()
    if service is None:
        return []

    try:
        import asyncio

        async def _search():
            results = await service.search_memory(
                app_name=app_name,
                user_id=user_id,
                query=query,
            )
            return [
                entry.content.parts[0].text
                for entry in results
                if entry.content and entry.content.parts
            ]

        return asyncio.run(_search())
    except Exception as exc:
        logger.warning("search_memory failed: %s", exc)
        return []


def get_session_memory(session_id: str) -> Dict[str, Any]:
    """Retrieve memory associated with a session.

    Args:
        session_id: Session identifier.

    Returns:
        Dict with session memory data. Empty dict on failure.
    """
    # Session memory is handled by ADK's session service, not Memory Bank
    return {}
