"""Contract tests: Independent Verification (SPEC-001 Steps 5-6).

Tests the VerifierRegistry and concrete GitHub API verifiers.

Architecture rule tested: **If no verifier exists for a claim type,
the claim stays UNVERIFIED. Inference alone cannot upgrade to
INDEPENDENTLY_VERIFIED.**
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from forgemind.verification import VerifierRegistry
from forgemind.verification.github_verifiers import (
    verify_ci_status,
    verify_dependency_change,
    verify_deployment_status,
)
from forgemind.validator import ClaimStatus, CrossLifecycleValidator


# -- VerifierRegistry -------------------------------------------------------


class TestVerifierRegistry:
    """VerifierRegistry maps claim types to verification backends."""

    def setup_method(self):
        """Clear registry before each test."""
        self._original = dict(VerifierRegistry._verifiers)
        VerifierRegistry._verifiers = {}

    def teardown_method(self):
        """Restore registry after each test."""
        VerifierRegistry._verifiers = self._original

    def test_register_and_verify(self):
        """A registered verifier is called for matching claim types."""
        mock_verifier = MagicMock(return_value=ClaimStatus.INDEPENDENTLY_VERIFIED)
        VerifierRegistry.register("ci_status", mock_verifier)

        claim = {"claim": "CI passed"}
        result = VerifierRegistry.verify(claim, "owner/repo", "abc123")

        assert result == ClaimStatus.INDEPENDENTLY_VERIFIED
        mock_verifier.assert_called_once_with(claim, "owner/repo", "abc123")

    def test_no_verifier_returns_unverified(self):
        """If no verifier exists, claim stays UNVERIFIED."""
        claim = {"claim": "some unknown claim type"}
        result = VerifierRegistry.verify(claim, "owner/repo", "abc123")
        assert result == ClaimStatus.UNVERIFIED

    def test_verifier_exception_returns_unverified(self):
        """If verifier raises, claim stays UNVERIFIED."""
        mock_verifier = MagicMock(side_effect=RuntimeError("API down"))
        VerifierRegistry.register("ci_status", mock_verifier)

        claim = {"claim": "CI passed"}
        result = VerifierRegistry.verify(claim, "owner/repo", "abc123")
        assert result == ClaimStatus.UNVERIFIED

    def test_classify_ci_status(self):
        """CI/build claims are classified as ci_status."""
        assert VerifierRegistry._classify_claim({"claim": "CI passed"}) == "ci_status"
        assert VerifierRegistry._classify_claim({"claim": "build failed"}) == "ci_status"

    def test_classify_dependency_change(self):
        """Dependency claims are classified as dependency_change."""
        assert (
            VerifierRegistry._classify_claim({"claim": "package.json changed"})
            == "dependency_change"
        )
        assert (
            VerifierRegistry._classify_claim({"claim": "dependency updated"})
            == "dependency_change"
        )

    def test_classify_deployment_status(self):
        """Deployment claims are classified as deployment_status."""
        assert (
            VerifierRegistry._classify_claim({"claim": "deployed to production"})
            == "deployment_status"
        )

    def test_classify_security_scan(self):
        """Security claims are classified as security_scan."""
        assert (
            VerifierRegistry._classify_claim({"claim": "vulnerability found"})
            == "security_scan"
        )

    def test_classify_unknown(self):
        """Unknown claims return 'unknown' type."""
        assert VerifierRegistry._classify_claim({"claim": "random text"}) == "unknown"

    def test_registered_types(self):
        """registered_types returns sorted list of registered types."""
        VerifierRegistry.register("z_type", MagicMock())
        VerifierRegistry.register("a_type", MagicMock())
        assert VerifierRegistry.registered_types() == ["a_type", "z_type"]


# -- verify_ci_status --------------------------------------------------------


class TestVerifyCIStatus:
    """verify_ci_status queries GitHub Check Runs API."""

    def test_confirms_passed_ci(self):
        """Returns INDEPENDENTLY_VERIFIED when check runs show success."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "check_runs": [
                {
                    "status": "completed",
                    "conclusion": "success",
                    "name": "test",
                }
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "CI passed"}
            result = verify_ci_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.INDEPENDENTLY_VERIFIED

    def test_confirms_failed_ci(self):
        """Returns INDEPENDENTLY_VERIFIED when check runs show failure."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "check_runs": [
                {
                    "status": "completed",
                    "conclusion": "failure",
                    "name": "test",
                }
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "CI failed"}
            result = verify_ci_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.INDEPENDENTLY_VERIFIED

    def test_contradicts_claim(self):
        """Returns UNVERIFIED when check runs contradict the claim."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "check_runs": [
                {
                    "status": "completed",
                    "conclusion": "success",
                    "name": "test",
                }
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "CI failed"}
            result = verify_ci_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED

    def test_no_check_runs(self):
        """Returns UNVERIFIED when no check runs exist."""
        mock_client = MagicMock()
        mock_client.get.return_value = {"check_runs": []}
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "CI passed"}
            result = verify_ci_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED

    def test_incomplete_check_runs(self):
        """Returns UNVERIFIED when check runs haven't completed."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "check_runs": [
                {
                    "status": "in_progress",
                    "conclusion": None,
                    "name": "test",
                }
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "CI passed"}
            result = verify_ci_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED

    def test_api_error_returns_unverified(self):
        """Returns UNVERIFIED on API errors."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "CI passed"}
            result = verify_ci_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED

    def test_ambiguous_claim_returns_unverified(self):
        """Returns UNVERIFIED when claim doesn't specify pass/fail."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "check_runs": [
                {
                    "status": "completed",
                    "conclusion": "success",
                    "name": "test",
                }
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "CI ran"}
            result = verify_ci_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED


# -- verify_dependency_change ------------------------------------------------


class TestVerifyDependencyChange:
    """verify_dependency_change queries GitHub Commits API."""

    def test_confirms_package_json_change(self):
        """Returns INDEPENDENTLY_VERIFIED when package.json changed."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "files": [
                {"filename": "package.json", "status": "modified"},
                {"filename": "src/index.js", "status": "modified"},
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "package.json changed"}
            result = verify_dependency_change(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.INDEPENDENTLY_VERIFIED

    def test_confirms_requirements_txt_change(self):
        """Returns INDEPENDENTLY_VERIFIED when requirements.txt changed."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "files": [
                {"filename": "requirements.txt", "status": "modified"},
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "requirements.txt updated"}
            result = verify_dependency_change(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.INDEPENDENTLY_VERIFIED

    def test_no_dependency_change(self):
        """Returns UNVERIFIED when no dependency files changed."""
        mock_client = MagicMock()
        mock_client.get.return_value = {
            "files": [
                {"filename": "src/index.js", "status": "modified"},
            ]
        }
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "package.json changed"}
            result = verify_dependency_change(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED

    def test_api_error_returns_unverified(self):
        """Returns UNVERIFIED on API errors."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "package.json changed"}
            result = verify_dependency_change(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED


# -- verify_deployment_status -----------------------------------------------


class TestVerifyDeploymentStatus:
    """verify_deployment_status queries GitHub Deployments API."""

    def test_confirms_successful_deployment(self):
        """Returns INDEPENDENTLY_VERIFIED when deployment succeeded."""
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            # First call: list deployments
            [{"id": 1, "sha": "abc123", "environment": "production"}],
            # Second call: deployment statuses
            [{"state": "success", "description": "Deployed"}],
        ]
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "deployed to production"}
            result = verify_deployment_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.INDEPENDENTLY_VERIFIED

    def test_confirms_failed_deployment(self):
        """Returns INDEPENDENTLY_VERIFIED when deployment failed."""
        mock_client = MagicMock()
        mock_client.get.side_effect = [
            [{"id": 1, "sha": "abc123", "environment": "production"}],
            [{"state": "failure", "description": "Failed"}],
        ]
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "deployment failed"}
            result = verify_deployment_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.INDEPENDENTLY_VERIFIED

    def test_no_deployments(self):
        """Returns UNVERIFIED when no deployments exist."""
        mock_client = MagicMock()
        mock_client.get.return_value = []
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "deployed to production"}
            result = verify_deployment_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED

    def test_api_error_returns_unverified(self):
        """Returns UNVERIFIED on API errors."""
        mock_client = MagicMock()
        mock_client.get.side_effect = Exception("Network error")
        with patch(
            "forgemind.verification.github_verifiers._get_client",
            return_value=mock_client,
        ):
            claim = {"claim": "deployed to production"}
            result = verify_deployment_status(claim, "owner/repo", "abc123")
            assert result == ClaimStatus.UNVERIFIED


# -- Integration: _verify_claim_provenance with VerifierRegistry -----------


class TestVerifyClaimProvenanceIntegration:
    """Integration tests for _verify_claim_provenance with VerifierRegistry."""

    def setup_method(self):
        """Clear registry before each test."""
        self._original = dict(VerifierRegistry._verifiers)
        VerifierRegistry._verifiers = {}

    def teardown_method(self):
        """Restore registry after each test."""
        VerifierRegistry._verifiers = self._original

    def test_local_matching_without_repo_sha(self):
        """Without repo/sha, falls back to cross-domain matching."""
        findings = [
            {"domain": "code", "supported_claims": ["CI passed"]},
            {"domain": "delivery", "supported_claims": ["CI passed"]},
        ]
        result = CrossLifecycleValidator._verify_claim_provenance(findings)
        assert result["CI passed"] == ClaimStatus.SUPPORTED.value

    def test_unverified_without_repo_sha(self):
        """Without repo/sha, single-domain claims stay UNVERIFIED."""
        findings = [
            {"domain": "code", "supported_claims": ["CI passed"]},
        ]
        result = CrossLifecycleValidator._verify_claim_provenance(findings)
        assert result["CI passed"] == ClaimStatus.UNVERIFIED.value

    def test_independently_verified_with_repo_sha(self):
        """With repo/sha and matching verifier, claim is INDEPENDENTLY_VERIFIED."""
        mock_verifier = MagicMock(return_value=ClaimStatus.INDEPENDENTLY_VERIFIED)
        VerifierRegistry.register("ci_status", mock_verifier)

        findings = [
            {"domain": "code", "supported_claims": ["CI passed"]},
        ]
        result = CrossLifecycleValidator._verify_claim_provenance(
            findings, repo="owner/repo", sha="abc123"
        )
        assert result["CI passed"] == ClaimStatus.INDEPENDENTLY_VERIFIED.value
        mock_verifier.assert_called_once()

    def test_no_verifier_falls_back_to_supported(self):
        """When no verifier exists, falls back to cross-domain matching."""
        findings = [
            {"domain": "code", "supported_claims": ["random claim"]},
            {"domain": "delivery", "supported_claims": ["random claim"]},
        ]
        result = CrossLifecycleValidator._verify_claim_provenance(
            findings, repo="owner/repo", sha="abc123"
        )
        assert result["random claim"] == ClaimStatus.SUPPORTED.value

    def test_no_verifier_single_domain_stays_unverified(self):
        """When no verifier exists and single domain, stays UNVERIFIED."""
        findings = [
            {"domain": "code", "supported_claims": ["random claim"]},
        ]
        result = CrossLifecycleValidator._verify_claim_provenance(
            findings, repo="owner/repo", sha="abc123"
        )
        assert result["random claim"] == ClaimStatus.UNVERIFIED.value

    def test_verifier_returns_unverified_falls_back(self):
        """When verifier returns UNVERIFIED, falls back to cross-domain matching."""
        mock_verifier = MagicMock(return_value=ClaimStatus.UNVERIFIED)
        VerifierRegistry.register("ci_status", mock_verifier)

        findings = [
            {"domain": "code", "supported_claims": ["CI passed"]},
            {"domain": "delivery", "supported_claims": ["CI passed"]},
        ]
        result = CrossLifecycleValidator._verify_claim_provenance(
            findings, repo="owner/repo", sha="abc123"
        )
        # Verifier returned UNVERIFIED, so falls back to cross-domain → SUPPORTED
        assert result["CI passed"] == ClaimStatus.SUPPORTED.value

    def test_verifier_exception_falls_back(self):
        """When verifier raises, falls back to cross-domain matching."""
        mock_verifier = MagicMock(side_effect=Exception("API down"))
        VerifierRegistry.register("ci_status", mock_verifier)

        findings = [
            {"domain": "code", "supported_claims": ["CI passed"]},
            {"domain": "delivery", "supported_claims": ["CI passed"]},
        ]
        result = CrossLifecycleValidator._verify_claim_provenance(
            findings, repo="owner/repo", sha="abc123"
        )
        # Verifier raised, so falls back to cross-domain → SUPPORTED
        assert result["CI passed"] == ClaimStatus.SUPPORTED.value


# -- validate() with repo/sha parameters ------------------------------------


class TestValidateWithRepoSha:
    """Test that validate() accepts and passes repo/sha parameters."""

    def test_validate_accepts_repo_sha(self):
        """validate() accepts repo and sha parameters."""
        from forgemind.acquisition import acquire_event

        event = {
            "event_id": "EVT-test-001",
            "situation_id": "SIT-test-001",
            "type": "pr",
            "source": "github",
            "summary": "Test PR",
            "timestamp": "2024-01-01T00:00:00Z",
            "reference": "https://github.com/owner/repo/pull/1",
            "affected_entities": ["repo"],
            "provenance": {"source": "test"},
        }
        acquired = acquire_event(event)
        plan = acquired["coverage_plan"]

        validator = CrossLifecycleValidator()
        # Should not raise
        result = validator.validate(
            plan,
            [],
            repo="owner/repo",
            sha="abc123",
        )
        assert result is not None
        assert "claim_statuses" in result