"""GitHub API client wrapper for ForgeMind ADK tools.

Provides a thin, typed wrapper around the GitHub REST API using the ``requests``
library (already a project dependency). Handles authentication, rate-limit
detection, pagination, and error normalization so individual tools stay
focused on their domain logic.

Environment:
    GITHUB_TOKEN: A GitHub personal access token (PAT) or fine-grained token.
        Required for authenticated requests (higher rate limits, access to
        private repos, and write operations). If unset, requests are made
        anonymously (60 req/hr, public repos only).

Usage::

    client = GitHubClient()
    response = client.get("repos/owner/repo/pulls/1")
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

__all__ = ["GitHubClient", "GitHubError"]

#: Base URL for the GitHub REST API.
GITHUB_API_BASE = "https://api.github.com"

#: Default timeout (seconds) for all API requests.
DEFAULT_TIMEOUT = 30

#: Environment variable name for the GitHub token.
TOKEN_ENV = "GITHUB_TOKEN"


class GitHubError(Exception):
    """Raised when a GitHub API request fails.

    Attributes:
        status_code: HTTP status code (0 if the request never reached GitHub).
        message: Human-readable error description.
        response_body: Raw response body for debugging.
    """

    def __init__(
        self,
        message: str,
        status_code: int = 0,
        response_body: Optional[str] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.response_body = response_body

    def to_dict(self) -> Dict[str, Any]:
        """Convert to a structured error dict suitable for tool return values."""
        result: Dict[str, Any] = {
            "error": True,
            "status_code": self.status_code,
            "message": self.message,
        }
        if self.response_body is not None:
            result["response_body"] = self.response_body
        return result


class GitHubClient:
    """Stateless GitHub API client wrapper.

    All methods return parsed JSON (dict/list) on success or raise
    :class:`GitHubError` on failure. Callers are expected to catch
    ``GitHubError`` and convert it to a tool-friendly error dict.

    The client is thread-safe (uses a fresh ``requests.Session`` per call
    by default; callers may pass a shared session for connection pooling).
    """

    def __init__(
        self,
        token: Optional[str] = None,
        base_url: str = GITHUB_API_BASE,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        """Initialize the GitHub client.

        Args:
            token: GitHub PAT. If None, reads from ``GITHUB_TOKEN`` env var.
            base_url: GitHub API base URL (override for GitHub Enterprise).
            timeout: Request timeout in seconds.
        """
        self._token = token or os.environ.get(TOKEN_ENV)
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    @property
    def is_authenticated(self) -> bool:
        """True if a token is configured (authenticated requests)."""
        return bool(self._token)

    def _headers(self) -> Dict[str, str]:
        """Build default headers for every request."""
        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        raw: bool = False,
    ) -> Any:
        """Make an authenticated request to the GitHub API.

        Args:
            method: HTTP method (GET, POST, PATCH, etc.).
            path: API path relative to base URL (e.g. ``repos/owner/repo/issues``).
            params: Optional query parameters.
            json: Optional JSON request body.
            raw: If True, return the raw response text instead of parsed JSON.

        Returns:
            Parsed JSON (dict/list) or raw text if ``raw=True``.

        Raises:
            GitHubError: On HTTP errors, network failures, or malformed responses.
        """
        url = f"{self._base_url}/{path.lstrip('/')}"
        try:
            response = requests.request(
                method,
                url,
                headers=self._headers(),
                params=params,
                json=json,
                timeout=self._timeout,
            )
        except requests.exceptions.Timeout as exc:
            raise GitHubError(
                f"Request to {path} timed out after {self._timeout}s",
                status_code=0,
            ) from exc
        except requests.exceptions.ConnectionError as exc:
            raise GitHubError(
                f"Connection error reaching GitHub API: {exc}",
                status_code=0,
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise GitHubError(
                f"Request to {path} failed: {exc}",
                status_code=0,
            ) from exc

        # Handle rate limiting explicitly for clearer error messages.
        if response.status_code == 403 and "rate limit" in response.text.lower():
            reset = response.headers.get("X-RateLimit-Reset", "unknown")
            raise GitHubError(
                f"GitHub API rate limit exceeded (resets at {reset})",
                status_code=403,
                response_body=response.text[:1000],
            )

        if response.status_code == 404:
            raise GitHubError(
                f"Resource not found: {path}",
                status_code=404,
                response_body=response.text[:1000],
            )

        if response.status_code == 401:
            raise GitHubError(
                "GitHub API authentication failed (invalid or expired token)",
                status_code=401,
                response_body=response.text[:1000],
            )

        if not response.ok:
            raise GitHubError(
                f"GitHub API returned {response.status_code} for {path}",
                status_code=response.status_code,
                response_body=response.text[:1000],
            )

        if raw:
            return response.text

        # Some endpoints return empty bodies (e.g. 204 No Content).
        if not response.content:
            return {}

        try:
            return response.json()
        except ValueError as exc:
            raise GitHubError(
                f"Failed to parse JSON response from {path}",
                status_code=response.status_code,
                response_body=response.text[:1000],
            ) from exc

    def get(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        raw: bool = False,
    ) -> Any:
        """Convenience method for GET requests."""
        return self._request("GET", path, params=params, raw=raw)

    def post(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Convenience method for POST requests."""
        return self._request("POST", path, json=json)

    def patch(
        self,
        path: str,
        *,
        json: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """Convenience method for PATCH requests."""
        return self._request("PATCH", path, json=json)

    def paginate(
        self,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        max_pages: int = 10,
    ) -> List[Dict[str, Any]]:
        """Fetch a paginated GitHub API endpoint and return all results.

        Follows the ``Link`` header to collect up to ``max_pages`` pages.

        Args:
            path: API path.
            params: Query parameters (per_page is set to 100 automatically).
            max_pages: Maximum number of pages to fetch (safety limit).

        Returns:
            A flat list of all items across pages.
        """
        if params is None:
            params = {}
        params.setdefault("per_page", 100)
        all_items: List[Dict[str, Any]] = []
        page = 1
        while page <= max_pages:
            params["page"] = page
            items = self.get(path, params=params)
            if not isinstance(items, list):
                break
            if not items:
                break
            all_items.extend(items)
            if len(items) < params["per_page"]:
                break
            page += 1
        return all_items