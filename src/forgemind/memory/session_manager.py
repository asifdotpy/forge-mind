"""Session state management for ForgeMind ADK agents.

Provides session creation, retrieval, and state persistence.
Falls back to in-memory storage when ADK session service is unavailable.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# In-memory session store (fallback when ADK session service is unavailable)
_sessions: Dict[str, Dict[str, Any]] = {}


def create_session(app_name: str, user_id: str) -> Dict[str, Any]:
    """Create a new session.

    Args:
        app_name: Logical application name.
        user_id: User identifier.

    Returns:
        Session dict with session_id, app_name, user_id, and state.
    """
    session_id = str(uuid.uuid4())
    session = {
        "session_id": session_id,
        "app_name": app_name,
        "user_id": user_id,
        "state": {},
    }
    _sessions[session_id] = session
    logger.debug("Created session: %s", session_id)
    return session


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a session by ID.

    Args:
        session_id: Session identifier.

    Returns:
        Session dict or None if not found.
    """
    return _sessions.get(session_id)


def save_state(session_id: str, key: str, value: Any) -> bool:
    """Save a value to session state.

    Args:
        session_id: Session identifier.
        key: State key.
        value: Value to store.

    Returns:
        True if saved successfully, False if session not found.
    """
    session = _sessions.get(session_id)
    if session is None:
        return False
    session["state"][key] = value
    return True


def load_state(session_id: str, key: str) -> Any:
    """Load a value from session state.

    Args:
        session_id: Session identifier.
        key: State key.

    Returns:
        Stored value or None if not found.
    """
    session = _sessions.get(session_id)
    if session is None:
        return None
    return session["state"].get(key)
