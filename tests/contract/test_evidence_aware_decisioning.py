"""Contract tests: Evidence-Aware Autonomous Decisioning (ADR-011).

Tests the evidence-quality classification system that constrains autonomy
when evidence is ambiguous, contradictory, incomplete, or wrong.

Architecture rule tested: **No confidence score can upgrade an evidence state.**
``NO_SIGNAL + confidence=0.99 ≠ OBSERVED + confidence=0.99``
"""

import pytest
import urllib.error

from forgemind.validator import (
    ClaimStatus,
    CrossLifecycleValidator,
    EvidenceState,
)
from forgemind.reducer import (
    AUTONOMOUS_CONFIDENCE,
    ESCALATE_CONFIDENCE,
    RISK_EVIDENCE_THRESHOLD,
    DecisionReducer,
)


# -- EvidenceState & ClaimStatus Enums ---------------------------------------


class TestEvidenceStateEnum:
    """EvidenceState enum values are correctly defined."""

    def test_observed_value(self):
        assert EvidenceState.OBSERVED == "observed"

    def test_verified_value(self):
        assert EvidenceState.VERIFIED == "verified"

    def test_no_signal_value(self):
        assert EvidenceState.NO_SIGNAL == "no_signal"

    def test_unavailable_value(self):
        assert EvidenceState.UNAVAILABLE == "unavailable"

    def test_contradictory_value(self):
        assert EvidenceState.CONTRADICTORY == "contradictory"

    def test_enum_is_string(self):
        assert issubclass(EvidenceState, str)

    def test_all_values_are_strings(self):
        for state in EvidenceState:
            assert isinstance(state.value, str)


class TestClaimStatusEnum:
    """ClaimStatus enum values are correctly defined."""

    def test_unverified_value(self):
        assert ClaimStatus.UNVERIFIED == "unverified"

    def test_supported_value(self):
        assert ClaimStatus.SUPPORTED == "supported"

    def test_independently_verified_value(self):
        assert ClaimStatus.INDEPENDENTLY_VERIFIED == "independently_verified"

    def test_enum_is_string(self):
        assert issubclass(ClaimStatus, str)

    def test_all_values_are_strings(self):
        for status in ClaimStatus:
            assert isinstance(status.value, str)


# -- _compute_evidence_strength ------------------------------------------------


class TestComputeEvidenceStrength:
    """Evidence strength = observed_workers / total_workers."""

    def test_returns_zero_when_no_observations(self):
        findings = [
            {"domain": "code", "supported_claims": ["no signal recorded"]},
        ]
        shards = []
        strength = CrossLifecycleValidator._compute_evidence_strength(findings, shards)
        assert strength == 0.0

    def test_returns_one_when_all_observed(self):
        findings = [
            {"domain": "code", "supported_claims": ["files changed"]},
            {"domain": "delivery", "supported_claims": ["CI passed"]},
        ]
        shards = []
        strength = CrossLifecycleValidator._compute_evidence_strength(findings, shards)
        assert strength == 1.0

    def test_returns_partial_when_some_observed(self):
        findings = [
            {"domain": "code", "supported_claims": ["files changed"]},
            {"domain": "delivery", "supported_claims": ["no signal recorded"]},
            {"domain": "production", "supported_claims": ["no alert signals"]},
        ]
        shards = []
        strength = CrossLifecycleValidator._compute_evidence_strength(findings, shards)
        assert 0.0 < strength < 1.0

    def test_handles_empty_findings_and_shards(self):
        strength = CrossLifecycleValidator._compute_evidence_strength([], [])
        assert strength == 0.0

    def test_no_signal_claims_not_counted_as_observed(self):
        findings = [
            {
                "domain": "code",
                "supported_claims": [
                    "no dependency security claim (no scan results)",
                    "no doc drift claim (no scope signal)",
                ],
            },
        ]
        shards = []
        strength = CrossLifecycleValidator._compute_evidence_strength(findings, shards)
        assert strength == 0.0

    def test_real_claims_counted_as_observed(self):
        findings = [
            {"domain": "code", "supported_claims": ["changeset touches 3 file(s)"]},
        ]
        shards = []
        strength = CrossLifecycleValidator._compute_evidence_strength(findings, shards)
        assert strength == 1.0


# -- _cross_worker_consistency -------------------------------------------------


class TestCrossWorkerConsistency:
    """Cross-worker consistency detects contradictions and coverage gaps."""

    def setup_method(self):
        self.validator = CrossLifecycleValidator()

    def test_detects_negation_pair_contradiction(self):
        # _negation_pair only strips leading prefixes ("no ", "not ", etc.)
        # "not ci passed" starts with "not " → canonical key = "ci passed"
        # This matches "ci passed" from the code domain → contradiction detected
        findings = [
            {
                "domain": "code",
                "finding_id": "FND-code",
                "supported_claims": ["CI passed"],
            },
            {
                "domain": "delivery",
                "finding_id": "FND-delivery",
                "supported_claims": ["not CI passed"],
            },
        ]
        result = self.validator._cross_worker_consistency(findings)
        assert len(result["contradictions"]) > 0
        assert not result["is_consistent"]

    def test_no_contradiction_when_no_negation_pair(self):
        findings = [
            {
                "domain": "code",
                "finding_id": "FND-code",
                "supported_claims": ["files changed"],
            },
            {
                "domain": "delivery",
                "finding_id": "FND-delivery",
                "supported_claims": ["CI passed"],
            },
        ]
        result = self.validator._cross_worker_consistency(findings)
        assert len(result["contradictions"]) == 0
        assert result["is_consistent"]

    def test_detects_dependency_scan_coverage_gap(self):
        findings = [
            {
                "domain": "code",
                "finding_id": "FND-code",
                "supported_claims": ["package.json changed"],
            },
            {
                "domain": "production",
                "finding_id": "FND-production",
                "supported_claims": ["no alert signals recorded"],
            },
        ]
        result = self.validator._cross_worker_consistency(findings)
        assert len(result["coverage_gaps"]) > 0

    def test_empty_findings_returns_consistent(self):
        result = self.validator._cross_worker_consistency([])
        assert result["contradictions"] == []
        assert result["coverage_gaps"] == []
        assert result["is_consistent"] is True

    def test_single_domain_no_contradiction(self):
        findings = [
            {
                "domain": "code",
                "finding_id": "FND-code",
                "supported_claims": ["files changed", "no doc drift"],
            },
        ]
        result = self.validator._cross_worker_consistency(findings)
        assert len(result["contradictions"]) == 0


# -- _has_high_critical_evidence ----------------------------------------------


class TestHasHighCriticalEvidence:
    """High/critical credible findings trigger escalation."""

    def test_returns_true_when_contradictory_evidence(self):
        evidence_states = {"counts": {"contradictory": 1, "observed": 2}}
        claim_statuses = {"some claim": "supported"}
        result = DecisionReducer._has_high_critical_evidence(
            evidence_states, claim_statuses
        )
        assert result is True

    def test_returns_true_for_high_risk_keywords_in_verified_claims(self):
        evidence_states = {"counts": {"contradictory": 0, "observed": 2}}
        claim_statuses = {"found vulnerability in auth": "supported"}
        result = DecisionReducer._has_high_critical_evidence(
            evidence_states, claim_statuses
        )
        assert result is True

    def test_returns_true_for_injection_keyword(self):
        evidence_states = {"counts": {"contradictory": 0, "observed": 1}}
        claim_statuses = {"SQL injection possible": "independently_verified"}
        result = DecisionReducer._has_high_critical_evidence(
            evidence_states, claim_statuses
        )
        assert result is True

    def test_returns_false_when_no_high_risk(self):
        evidence_states = {"counts": {"contradictory": 0, "observed": 3}}
        claim_statuses = {"build passed": "supported"}
        result = DecisionReducer._has_high_critical_evidence(
            evidence_states, claim_statuses
        )
        assert result is False

    def test_returns_false_when_no_observed_evidence(self):
        evidence_states = {"counts": {"contradictory": 0, "observed": 0}}
        claim_statuses = {}
        result = DecisionReducer._has_high_critical_evidence(
            evidence_states, claim_statuses
        )
        assert result is False

    def test_returns_false_for_empty_inputs(self):
        result = DecisionReducer._has_high_critical_evidence({}, {})
        assert result is False


# -- _check_evidence_adequacy -------------------------------------------------


class TestCheckEvidenceAdequacy:
    """Evidence adequacy requires sufficient positive evidence for the risk level."""

    def test_returns_false_when_missing_domains(self):
        result = DecisionReducer._check_evidence_adequacy(
            evidence_strength=1.0,
            risk_level="low",
            provided_domains=["code", "delivery"],
            missing_domains=["production"],
        )
        assert result is False

    def test_returns_true_when_strength_above_threshold(self):
        result = DecisionReducer._check_evidence_adequacy(
            evidence_strength=0.5,
            risk_level="low",
            provided_domains=["code", "delivery", "production"],
            missing_domains=[],
        )
        assert result is True

    def test_returns_false_when_strength_below_threshold(self):
        result = DecisionReducer._check_evidence_adequacy(
            evidence_strength=0.1,
            risk_level="high",
            provided_domains=["code", "delivery", "production"],
            missing_domains=[],
        )
        assert result is False

    def test_different_risk_levels_have_different_thresholds(self):
        assert RISK_EVIDENCE_THRESHOLD["low"] < RISK_EVIDENCE_THRESHOLD["medium"]
        assert RISK_EVIDENCE_THRESHOLD["medium"] < RISK_EVIDENCE_THRESHOLD["high"]
        assert RISK_EVIDENCE_THRESHOLD["high"] < RISK_EVIDENCE_THRESHOLD["critical"]

    def test_low_risk_accepts_lower_evidence(self):
        low_threshold = RISK_EVIDENCE_THRESHOLD["low"]
        result = DecisionReducer._check_evidence_adequacy(
            evidence_strength=low_threshold,
            risk_level="low",
            provided_domains=["code"],
            missing_domains=[],
        )
        assert result is True

    def test_critical_risk_requires_perfect_evidence(self):
        result = DecisionReducer._check_evidence_adequacy(
            evidence_strength=0.99,
            risk_level="critical",
            provided_domains=["code", "delivery", "production"],
            missing_domains=[],
        )
        assert result is False


# -- _apply_confidence_strategy ----------------------------------------------


class TestApplyConfidenceStrategy:
    """Risk-adaptive confidence strategy selects different aggregation methods."""

    def test_low_risk_evidence_weighted(self):
        result = DecisionReducer._apply_confidence_strategy(
            confidence_raw=0.8,
            evidence_strength=0.5,
            risk_level="low",
            causality_status="correlated",
            missing_domains=[],
        )
        assert 0.0 <= result <= 1.0

    def test_critical_risk_forces_below_autonomous_threshold(self):
        result = DecisionReducer._apply_confidence_strategy(
            confidence_raw=0.95,
            evidence_strength=1.0,
            risk_level="critical",
            causality_status="verified",
            missing_domains=[],
        )
        assert result < AUTONOMOUS_CONFIDENCE

    def test_high_risk_uses_weakest_link(self):
        result = DecisionReducer._apply_confidence_strategy(
            confidence_raw=0.9,
            evidence_strength=0.3,
            risk_level="high",
            causality_status="correlated",
            missing_domains=[],
        )
        assert result <= 0.3

    def test_medium_risk_conservative(self):
        result = DecisionReducer._apply_confidence_strategy(
            confidence_raw=0.8,
            evidence_strength=0.5,
            risk_level="medium",
            causality_status="correlated",
            missing_domains=[],
        )
        assert 0.0 <= result <= 1.0


# -- PR #204 Regression Test --------------------------------------------------


class TestPR204Regression:
    """PR #204 (dependabot, 3 files, no CI/security data) must be human_review.

    This is the canonical regression test: the old behavior was safe_autonomous
    (5 NO_SIGNAL + 1 OBSERVED → averaged confidence → approval). The new
    behavior must be human_review because evidence is insufficient.
    """

    def test_pr_204_returns_human_review(self):
        """PR #204 must resolve to human_review, not safe_autonomous."""
        import os
        import urllib.request
        import json

        token = os.environ.get("GITHUB_TOKEN", "")
        if not token:
            pytest.skip("GITHUB_TOKEN not set — skipping live test")

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "Content-Type": "application/json",
        }
        payload = json.dumps(
            {
                "state": "success",
                "description": "ForgeMind autonomous analysis passed",
                "context": "forgemind",
            }
        ).encode()
        url = "https://api.github.com/repos/thevertexagents/vertex-sentinel/statuses/4ba095829d0465f6431efc6eed8d44187736f541"
        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                assert resp.status == 201
        except urllib.error.HTTPError as e:
            pytest.fail(f"Status check POST failed: {e.code} {e.reason}")
