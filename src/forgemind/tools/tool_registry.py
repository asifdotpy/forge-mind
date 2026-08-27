"""Tool registry for ForgeMind ADK agents.

Provides a registry pattern for mapping tool names to tool objects
so agents can be configured with tools=get_default_registry().tools
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry that maps tool names to callable tool functions.

    ADK agents accept a ``tools=[...]`` list in their constructor.
    This registry collects all available ForgeMind tools and exposes
    them as a list for agent configuration.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Callable[..., Any]] = {}

    def register(self, name: str, func: Callable[..., Any]) -> None:
        """Register a tool function under a given name."""
        self._tools[name] = func
        logger.debug("Registered tool: %s", name)

    def get(self, name: str) -> Callable[..., Any]:
        """Get a tool by name. Raises KeyError if not found."""
        return self._tools[name]

    @property
    def tools(self) -> List[Callable[..., Any]]:
        """Return all registered tools as a list for ADK agent configuration."""
        return list(self._tools.values())

    @property
    def names(self) -> List[str]:
        """Return all registered tool names."""
        return list(self._tools.keys())

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


def get_default_registry() -> ToolRegistry:
    """Build and return the default ForgeMind tool registry.

    Registers all GitHub tools and any other built-in tools.
    """
    registry = ToolRegistry()

    try:
        from forgemind.tools.github_tools import (
            get_changed_files,
            get_pr_details,
            get_pr_diff,
            get_repo_contributors,
            post_comment,
            search_issues,
            update_status_check,
        )

        registry.register("get_pr_details", get_pr_details)
        registry.register("get_pr_diff", get_pr_diff)
        registry.register("get_changed_files", get_changed_files)
        registry.register("post_comment", post_comment)
        registry.register("update_status_check", update_status_check)
        registry.register("get_repo_contributors", get_repo_contributors)
        registry.register("search_issues", search_issues)
    except ImportError as exc:
        logger.warning("Could not import GitHub tools: %s", exc)

    return registry
