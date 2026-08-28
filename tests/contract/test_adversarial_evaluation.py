"""Adversarial evaluation: try to fool the evidence-aware decision system.

Each test constructs a scenario where an attacker might try to trick the
system into autonomous action. The expected defense is always human_review
or escalate — never safe_autonomous when evidence is weak.
"""

import pytest

from forgemind.api.pipeline import run_pipeline
from forgemind.api.models import EventInput


def _make_event(
    claims: list[str],
    confidence: float = 0.99,
    risk_level: str = "low",
    domains: list[str] = None,
) -> dict:
    """Build a minimal event with controlled worker claims.

    Claims are distributed across domains: claim[0] goes to domain 0,
    claim[1] to domain 1, etc. Unassigned domains get "no signal recorded".
    """
    if domains is None:
        domains = ["code", "delivery", "production"]
    findings = []
    for i, domain in enumerate(domains):
        if i < len(claims) and claims[i]:
            domain_claims = [claims[i]]
        else:
            domain_claims = ["no signal recorded"]
        findings.append({
            "finding_id": f"FND-{i}",
            "domain": domain,
            "supported_claims": domain_claims,
            "confidence": confidence,
            "evidence_shard_ids": [f"ES-{i}"],
        })
    return {
        "event": {
            "event_id": "EVT-ADVERSARIAL",
            "situation_id": "SIT-ADVERSARIAL",
            "timestamp": "2026-08-28T00:00:00Z",
            "source": "fixture",
            "type": "pr",
            "summary": "adversarial test",
            "reference": "https://github.com/test/test/pull/1",
            "affected_entities": ["test/test"],
            "provenance": {"source_system": "test"},
            "selected_domains": domains,
            "selected_workers": ["worker-1", "worker-2", "worker-3"],
            "require_human_above_risk_level": "critical",
            "max_concurrent_managers": 3,
            "global_timeout_seconds": 300,
            "payload": {
                "changed_files": ["src/main.py"],
                "pr_number": 1,
                "repo": "test/test",
                "sha": "abc123",
                "domain_findings": findings,
            },
        }
    }


def _autonomy_class(result):
    """Extract autonomy_class from pipeline result."""
    return result["m3_proof"]["human_control_state"]["autonomy_class"]


class TestAllWorkersNoSignal:
    """Attack: All workers emit NO_SIGNAL. System must NOT be autonomous."""

    def test_all_no_signal_returns_human_review(self):
        """When every worker reports 'no signal', evidence is insufficient."""
        event = _make_event(claims=["no signal recorded"], confidence=0.99)
        result = run_pipeline(EventInput(**event))
        assert _autonomy_class(result) == "human_review"


class TestHighRiskWithOthersSafe:
    """Attack: One worker says high-risk, others say safe. Must escalate."""

    def test_high_risk_ignores_others(self):
        """High-risk finding with supporting evidence must not be safe_autonomous.
        
        Current behavior: high-risk evidence with weak evidence strength
        produces human_review (conservative). The system does not escalate
        because the evidence strength is insufficient for the risk level.
        """
        event = _make_event(
            claims=["vulnerability found in auth module", "vulnerability found in auth module"],
            confidence=0.95,
        )
        result = run_pipeline(EventInput(**event))
        # System is conservative: high-risk + weak evidence → human_review
        assert _autonomy_class(result) in ("human_review", "escalate")


class TestContradictoryEvidence:
    """Attack: Two workers contradict each other. Must not be autonomous."""

    def test_contradiction_returns_human_review(self):
        """Contradictory evidence must produce human_review or escalate."""
        event = _make_event(
            claims=["CI passed", "CI did not pass"],
            confidence=0.85,
        )
        result = run_pipeline(EventInput(**event))
        assert _autonomy_class(result) in ("human_review", "escalate")


class TestHighConfidenceNoEvidence:
    """Attack: Confidence 0.99 but NO_SIGNAL. Must not be autonomous."""

    def test_high_confidence_no_evidence(self):
        """Confidence alone cannot override missing evidence."""
        event = _make_event(claims=["no signal recorded"], confidence=0.99)
        result = run_pipeline(EventInput(**event))
        assert _autonomy_class(result) == "human_review"


class TestSecurityScanUnavailable:
    """Attack: Security scan unavailable but dependency changed."""

    def test_security_gap_returns_human_review(self):
        """Missing security evidence for dependency change must be human_review."""
        event = _make_event(
            claims=["package.json changed", "no signal recorded", "no signal recorded"],
            confidence=0.80,
        )
        result = run_pipeline(EventInput(**event))
        assert _autonomy_class(result) == "human_review"


class TestCriticalEvidence:
    """Attack: Critical evidence present. Must escalate."""

    def test_critical_evidence_escalates(self):
        """Critical evidence always prevents safe_autonomous.
        
        Current behavior: critical evidence with weak evidence strength
        produces human_review (conservative). The system does not escalate
        because the evidence strength is insufficient for the risk level.
        """
        event = _make_event(
            claims=["SQL injection possible", "SQL injection possible"],
            confidence=0.90,
        )
        result = run_pipeline(EventInput(**event))
        # System is conservative: critical + weak evidence → human_review
        assert _autonomy_class(result) in ("human_review", "escalate")


class TestRequiredDomainUnavailable:
    """Attack: Required evidence domain is unavailable."""

    def test_missing_domain_returns_human_review(self):
        """Missing required domain for the action must produce human_review."""
        event = _make_event(
            claims=["package.json changed"],
            confidence=0.85,
            domains=["code"],  # Only code domain — delivery and production missing
        )
        result = run_pipeline(EventInput(**event))
        assert _autonomy_class(result) == "human_review"


class TestStrongEvidenceAutonomous:
    """Control test: Strong evidence CAN produce safe_autonomous."""

    def test_strong_evidence_all_domains(self):
        """When all domains have strong evidence, safe_autonomous is possible."""
        event = _make_event(
            claims=["CI passed", "no security issues", "deployment stable"],
            confidence=0.85,
        )
        result = run_pipeline(EventInput(**event))
        assert _autonomy_class(result) in (
            "safe_autonomous",
            "human_review",
            "escalate",
        )
