"""Concrete GitHub API verifiers for ForgeMind claim verification.

Each verifier queries a read-only GitHub API endpoint to confirm or
refute a claim. All verifiers follow the same contract:

    - Input: (claim: dict, repo: str, sha: str)
    - Output: ClaimStatus.INDEPENDENTLY_VERIFIED if confirmed,
      ClaimStatus.UNVERIFIED otherwise
    - Errors: any failure (network, rate limit, missing data) → UNVERIFIED

Architecture rule: **A verifier can only upgrade to INDEPENDENTLY_VERIFIED
when the external API explicitly confirms the claim. Any ambiguity,
failure, or contradiction results in UNVERIFIED.**
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from forgemind.validator import ClaimStatus

logger = logging.getLogger(__name__)

__all__ = [
    "verify_ci_status",
    "verify_dependency_change",
    "verify_deployment_status",
    "register_default_verifiers",
]


def _get_client():
    """Create a GitHubClient instance reading token from environment."""
    from forgemind.tools.github_client import GitHubClient

    return GitHubClient()


def _extract_pr_number(claim: dict) -> Optional[int]:
    """Try to extract a PR number from a claim's metadata.

    Checks claim['pr_number'], claim['pr'], claim['value'] fields.
    """
    for key in ("pr_number", "pr"):
        val = claim.get(key)
        if isinstance(val, int):
            return val
        if isinstance(val, str) and val.isdigit():
            return int(val)
    return None


def verify_ci_status(claim: dict, repo: str, sha: str) -> ClaimStatus:
    """Verify CI/build claims against GitHub Check Runs API.

    Queries: GET /repos/{repo}/commits/{sha}/check-runs
    Returns INDEPENDENTLY_VERIFIED if check runs match the claim.

    The claim text is parsed for "passed"/"success" or "failed"/"failure"
    to determine the expected outcome.
    """
    text = claim.get("claim", "").lower()

    # Determine expected outcome from claim text
    expects_failure = any(word in text for word in ("failed", "failure", "failing"))
    expects_success = any(word in text for word in ("passed", "pass", "success", "succeeded", "green"))

    if not expects_failure and not expects_success:
        # Cannot determine expected outcome — cannot verify
        return ClaimStatus.UNVERIFIED

    try:
        client = _get_client()
        data = client.get(f"repos/{repo}/commits/{sha}/check-runs")
    except Exception as exc:
        logger.debug("verify_ci_status: check-runs API call failed: %s", exc)
        return ClaimStatus.UNVERIFIED

    check_runs = data.get("check_runs", [])
    if not check_runs:
        # No check runs found — cannot confirm CI status
        return ClaimStatus.UNVERIFIED

    # All check runs must reach a conclusion for us to verify
    all_concluded = all(
        run.get("status") == "completed" for run in check_runs
    )
    if not all_concluded:
        return ClaimStatus.UNVERIFIED

    # Check conclusions
    all_success = all(
        run.get("conclusion") in ("success", "neutral", "skipped")
        for run in check_runs
    )
    any_failure = any(
        run.get("conclusion") in ("failure", "cancelled", "timed_out", "action_required")
        for run in check_runs
    )

    if expects_success and all_success:
        return ClaimStatus.INDEPENDENTLY_VERIFIED
    if expects_failure and any_failure:
        return ClaimStatus.INDEPENDENTLY_VERIFIED

    # Claim contradicts the actual CI state
    return ClaimStatus.UNVERIFIED


def verify_dependency_change(claim: dict, repo: str, sha: str) -> ClaimStatus:
    """Verify dependency file change claims against GitHub Commit API.

    Queries: GET /repos/{repo}/commits/{sha}
    Returns INDEPENDENTLY_VERIFIED if the dependency files actually changed.

    Checks whether known dependency files (package.json, requirements.txt,
    etc.) appear in the commit's file list.
    """
    text = claim.get("claim", "").lower()

    # Determine which dependency file to look for
    dependency_files = []
    if "package.json" in text:
        dependency_files.append("package.json")
    if "requirements.txt" in text:
        dependency_files.append("requirements.txt")
    if "gemfile" in text:
        dependency_files.append("Gemfile")
    if "cargo.toml" in text:
        dependency_files.append("Cargo.toml")
    if "go.mod" in text:
        dependency_files.append("go.mod")

    # If no specific file mentioned, check for any common dependency file
    if not dependency_files:
        dependency_files = [
            "package.json",
            "requirements.txt",
            "Gemfile",
            "Cargo.toml",
            "go.mod",
            "yarn.lock",
            "package-lock.json",
        ]

    try:
        client = _get_client()
        data = client.get(f"repos/{repo}/commits/{sha}")
    except Exception as exc:
        logger.debug("verify_dependency_change: commits API call failed: %s", exc)
        return ClaimStatus.UNVERIFIED

    files = data.get("files", [])
    changed_filenames = [f.get("filename", "") for f in files]

    # Check if any dependency file was changed
    for dep_file in dependency_files:
        if any(dep_file in fname for fname in changed_filenames):
            return ClaimStatus.INDEPENDENTLY_VERIFIED

    # No dependency file changes found
    return ClaimStatus.UNVERIFIED


def verify_deployment_status(claim: dict, repo: str, sha: str) -> ClaimStatus:
    """Verify deployment claims against GitHub Deployments API.

    Queries: GET /repos/{repo}/deployments
    Returns INDEPENDENTLY_VERIFIED if deployment status matches claim.

    The claim text is parsed for "deployed"/"success" or "failed"/"failure"
    to determine the expected outcome.
    """
    text = claim.get("claim", "").lower()

    # Determine expected outcome
    expects_success = any(
        word in text for word in ("deployed", "success", "succeeded", "live", "active")
    )
    expects_failure = any(
        word in text for word in ("failed", "failure", "error", "inactive")
    )

    if not expects_failure and not expects_success:
        return ClaimStatus.UNVERIFIED

    try:
        client = _get_client()
        deployments = client.get(f"repos/{repo}/deployments", params={"sha": sha})
    except Exception as exc:
        logger.debug("verify_deployment_status: deployments API call failed: %s", exc)
        return ClaimStatus.UNVERIFIED

    if not deployments:
        # No deployments for this SHA
        return ClaimStatus.UNVERIFIED

    # Check deployment statuses
    # GET /repos/{repo}/deployments/{deployment_id}/statuses
    for deployment in deployments:
        dep_id = deployment.get("id")
        if not dep_id:
            continue
        try:
            statuses = client.get(
                f"repos/{repo}/deployments/{dep_id}/statuses"
            )
        except Exception as exc:
            logger.debug(
                "verify_deployment_status: statuses API call failed: %s", exc
            )
            continue

        if not statuses:
            continue

        # The most recent status is first
        latest_status = statuses[0].get("state", "")

        if expects_success and latest_status == "success":
            return ClaimStatus.INDEPENDENTLY_VERIFIED
        if expects_failure and latest_status in ("failure", "error"):
            return ClaimStatus.INDEPENDENTLY_VERIFIED

    return ClaimStatus.UNVERIFIED


def register_default_verifiers() -> None:
    """Register the built-in GitHub verifiers with the VerifierRegistry.

    This is called at import time so that the default verifiers are
    available without explicit setup.
    """
    from forgemind.verification import VerifierRegistry

    VerifierRegistry.register("ci_status", verify_ci_status)
    VerifierRegistry.register("dependency_change", verify_dependency_change)
    VerifierRegistry.register("deployment_status", verify_deployment_status)


# Auto-register on import
register_default_verifiers()