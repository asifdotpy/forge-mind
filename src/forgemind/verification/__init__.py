"""ForgeMind Independent Verification (SPEC-001 Steps 5-6).

Provides a registry-based system for verifying claims against external
systems of record (GitHub API). The critical architecture rule is:

    If no verifier exists for a claim type, the claim stays UNVERIFIED.
    Inference alone CANNOT upgrade to INDEPENDENTLY_VERIFIED.

This module implements the verification backends that query GitHub's
read-only APIs to confirm or refute claims made by workers.
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

from forgemind.validator import ClaimStatus

logger = logging.getLogger(__name__)

__all__ = ["VerifierRegistry"]

#: Type alias for verifier functions.
VerifierFn = Callable[[dict, str, str], ClaimStatus]


class VerifierRegistry:
    """Maps claim types to verification backends.

    Each verifier takes ``(claim, repo, sha)`` and returns:
    - :attr:`ClaimStatus.INDEPENDENTLY_VERIFIED` if external source confirms
    - :attr:`ClaimStatus.UNVERIFIED` if external source contradicts
      or no verifier exists

    Architecture rule: **If no verifier exists for a claim type, the claim
    stays UNVERIFIED. Inference alone cannot upgrade to
    INDEPENDENTLY_VERIFIED.**
    """

    _verifiers: dict[str, VerifierFn] = {}

    @classmethod
    def register(cls, claim_type: str, verifier: VerifierFn) -> None:
        """Register a verifier for a claim type.

        Args:
            claim_type: The claim type string (e.g., ``"ci_status"``).
            verifier: A callable with signature ``(claim, repo, sha)``.
        """
        cls._verifiers[claim_type] = verifier

    @classmethod
    def verify(cls, claim: dict, repo: str, sha: str) -> ClaimStatus:
        """Verify a claim against an external system of record.

        Args:
            claim: The structured claim dict with at least a ``"claim"`` key.
            repo: Repository in ``owner/repo`` format.
            sha: Commit SHA to verify against.

        Returns:
            :attr:`ClaimStatus.INDEPENDENTLY_VERIFIED` if a verifier exists
            AND the external source confirms the claim.
            :attr:`ClaimStatus.UNVERIFIED` otherwise (no verifier, API
            failure, or claim contradicts external data).
        """
        claim_type = cls._classify_claim(claim)
        verifier = cls._verifiers.get(claim_type)
        if verifier is None:
            logger.debug(
                "No verifier for claim type %r — claim stays UNVERIFIED",
                claim_type,
            )
            return ClaimStatus.UNVERIFIED
        try:
            return verifier(claim, repo, sha)
        except Exception as exc:
            logger.warning(
                "Verifier %s failed for claim %r: %s — claim stays UNVERIFIED",
                claim_type,
                claim.get("claim", ""),
                exc,
            )
            return ClaimStatus.UNVERIFIED

    @classmethod
    def _classify_claim(cls, claim: dict) -> str:
        """Map claim text to a claim type for verifier lookup.

        Uses keyword matching on the claim text to determine which
        verification backend (if any) should handle it.
        """
        text = claim.get("claim", "").lower()
        if "ci" in text or "build" in text:
            return "ci_status"
        if "dependency" in text or "package.json" in text:
            return "dependency_change"
        if "security" in text or "vulnerability" in text:
            return "security_scan"
        if "deploy" in text:
            return "deployment_status"
        return "unknown"

    @classmethod
    def registered_types(cls) -> list[str]:
        """Return a sorted list of currently registered claim types."""
        return sorted(cls._verifiers.keys())