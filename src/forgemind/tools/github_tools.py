"""GitHub API tools for ForgeMind ADK agents.

Each tool is a standalone function with type hints and docstrings
that ADK agents can call. All tools handle errors gracefully.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _get_token() -> Optional[str]:
    """Read GitHub token from environment."""
    return os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")


def get_pr_details(repo: str, pr_number: int) -> Dict[str, Any]:
    """Fetch details for a GitHub pull request.

    Args:
        repo: Repository in 'owner/repo' format.
        pr_number: Pull request number.

    Returns:
        Dict with PR details (title, body, author, state, etc.)
        or error dict on failure.
    """
    token = _get_token()
    if not token:
        return {"error": "GITHUB_TOKEN not configured"}
    try:
        from forgemind.tools.github_client import GitHubClient
        client = GitHubClient(token=token)
        return client.get(f"repos/{repo}/pulls/{pr_number}")
    except Exception as exc:
        logger.warning("get_pr_details failed: %s", exc)
        return {"error": str(exc)}


def get_pr_diff(repo: str, pr_number: int) -> str:
    """Fetch the full diff of a GitHub pull request.

    Args:
        repo: Repository in 'owner/repo' format.
        pr_number: Pull request number.

    Returns:
        The diff as a string, or error message on failure.
    """
    token = _get_token()
    if not token:
        return "Error: GITHUB_TOKEN not configured"
    try:
        from forgemind.tools.github_client import GitHubClient
        client = GitHubClient(token=token)
        return client.get(f"repos/{repo}/pulls/{pr_number}", raw=True)
    except Exception as exc:
        logger.warning("get_pr_diff failed: %s", exc)
        return f"Error: {exc}"


def get_changed_files(repo: str, pr_number: int) -> List[Dict[str, Any]]:
    """Get list of changed files in a pull request.

    Args:
        repo: Repository in 'owner/repo' format.
        pr_number: Pull request number.

    Returns:
        List of file dicts (filename, status, additions, deletions, patch)
        or error dict on failure.
    """
    token = _get_token()
    if not token:
        return [{"error": "GITHUB_TOKEN not configured"}]
    try:
        from forgemind.tools.github_client import GitHubClient
        client = GitHubClient(token=token)
        return client.get(f"repos/{repo}/pulls/{pr_number}/files")
    except Exception as exc:
        logger.warning("get_changed_files failed: %s", exc)
        return [{"error": str(exc)}]


def post_comment(repo: str, pr_number: int, body: str) -> Dict[str, Any]:
    """Post a comment on a GitHub pull request.

    Args:
        repo: Repository in 'owner/repo' format.
        pr_number: Pull request number.
        body: Comment text (Markdown supported).

    Returns:
        Dict with comment details or error dict on failure.
    """
    token = _get_token()
    if not token:
        return {"error": "GITHUB_TOKEN not configured"}
    try:
        from forgemind.tools.github_client import GitHubClient
        client = GitHubClient(token=token)
        return client.post(
            f"repos/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
    except Exception as exc:
        logger.warning("post_comment failed: %s", exc)
        return {"error": str(exc)}


def update_status_check(
    repo: str,
    sha: str,
    state: str,
    description: str,
    context: str = "forgemind",
) -> Dict[str, Any]:
    """Update a commit status check on GitHub.

    Args:
        repo: Repository in 'owner/repo' format.
        sha: Commit SHA.
        state: One of 'pending', 'success', 'failure', 'error'.
        description: Short description of the status.
        context: Status check name (default: 'forgemind').

    Returns:
        Dict with status details or error dict on failure.
    """
    token = _get_token()
    if not token:
        return {"error": "GITHUB_TOKEN not configured"}
    try:
        from forgemind.tools.github_client import GitHubClient
        client = GitHubClient(token=token)
        return client.post(
            f"repos/{repo}/statuses/{sha}",
            json={
                "state": state,
                "description": description,
                "context": context,
            },
        )
    except Exception as exc:
        logger.warning("update_status_check failed: %s", exc)
        return {"error": str(exc)}


def get_repo_contributors(repo: str) -> List[Dict[str, Any]]:
    """Get list of contributors for a repository.

    Args:
        repo: Repository in 'owner/repo' format.

    Returns:
        List of contributor dicts or error dict on failure.
    """
    token = _get_token()
    if not token:
        return [{"error": "GITHUB_TOKEN not configured"}]
    try:
        from forgemind.tools.github_client import GitHubClient
        client = GitHubClient(token=token)
        return client.paginate(f"repos/{repo}/contributors")
    except Exception as exc:
        logger.warning("get_repo_contributors failed: %s", exc)
        return [{"error": str(exc)}]


def search_issues(repo: str, query: str) -> List[Dict[str, Any]]:
    """Search for issues and PRs in a repository.

    Args:
        repo: Repository in 'owner/repo' format.
        query: Search query string.

    Returns:
        List of issue/PR dicts or error dict on failure.
    """
    token = _get_token()
    if not token:
        return [{"error": "GITHUB_TOKEN not configured"}]
    try:
        from forgemind.tools.github_client import GitHubClient
        client = GitHubClient(token=token)
        return client.get(
            "search/issues",
            params={"q": f"repo:{repo} {query}"},
        ).get("items", [])
    except Exception as exc:
        logger.warning("search_issues failed: %s", exc)
        return [{"error": str(exc)}]
