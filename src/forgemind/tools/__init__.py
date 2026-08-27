"""GitHub Tool Implementation for ForgeMind ADK agents.

This package provides ADK-compatible tools that agents can call to interact
with GitHub repositories — fetching PR details, posting comments, managing
status checks, and querying repository metadata.
"""

from forgemind.tools.github_tools import (
    get_changed_files,
    get_pr_details,
    get_pr_diff,
    get_repo_contributors,
    post_comment,
    search_issues,
    update_status_check,
)
from forgemind.tools.tool_registry import ToolRegistry, get_default_registry

__all__ = [
    "GitHubClient",
    "ToolRegistry",
    "get_default_registry",
    "get_changed_files",
    "get_pr_details",
    "get_pr_diff",
    "get_repo_contributors",
    "post_comment",
    "search_issues",
    "update_status_check",
]
