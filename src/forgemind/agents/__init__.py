"""ADK agent composition for ForgeMind.

Package home for the ADK agent builders (root agent, per-tier wrappers).
Imported lazily by :mod:`forgemind.adk_app` so the package boots cleanly
without google-adk installed.
"""

from __future__ import annotations

__all__ = ["build_root_agent"]