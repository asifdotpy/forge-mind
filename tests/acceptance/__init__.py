"""SPEC-002 Phase 4 — hardened acceptance test.

Runs the canonical ``EVT-REAL-001`` payload through ``run_pipeline`` and
asserts the five properties SPEC-002 §5 requires of any self-contained
event (no ``workers`` key):

1. ``evidence_shards >= 1``
2. ``domain_findings >= 1``
3. ``validated_situation.confidence > 0.0``
4. ``terminal.type in {"action", "escalation"}``
5. ``m3_proof.provenance_links.artifact_chain`` has >= 7 nodes

The test is deterministic — no API calls, no credentials.  It is the
SPEC-002 Phase 4 gate and is discoverable by pytest as part of the
``tests/acceptance/`` suite.
"""

from forgemind.api import EventInput, run_pipeline

# Canonical SPEC-002 §5.3 payload (self-contained — no ``workers`` key).
EVT_REAL_001 = {
    "event_id": "EVT-REAL-001",
    "situation_id": "SIT-REAL-001",
    "timestamp": "2026-08-25T10:00:00Z",
    "source": "github",
    "type": "pr",
    "summary": "Refactor auth middleware",
    "reference": "refs/heads/feature/auth",
    "affected_entities": ["auth-service"],
    "provenance": {"source_system": "github"},
    "selected_domains": ["code"],
    "selected_workers": ["pr-pre-flight-ast-worker"],
    "require_human_above_risk_level": "critical",
    "max_concurrent_managers": 3,
    "global_timeout_seconds": 300,
    "payload": {"changed_files": ["auth/middleware.py", "auth/token.py"]},
}


def test_evt_real_001_produces_evidence():
    """A self-contained event yields at least one EvidenceShard."""
    result = run_pipeline(EventInput(**EVT_REAL_001))
    shards = result["artifacts"]["evidence_shards"]
    assert len(shards) >= 1, f"expected >= 1 shard, got {len(shards)}"


def test_evt_real_001_produces_domain_findings():
    """A self-contained event yields at least one DomainFinding."""
    result = run_pipeline(EventInput(**EVT_REAL_001))
    findings = result["artifacts"]["domain_findings"]
    assert len(findings) >= 1, f"expected >= 1 finding, got {len(findings)}"


def test_evt_real_001_confidence_positive():
    """The validated situation carries positive confidence."""
    result = run_pipeline(EventInput(**EVT_REAL_001))
    confidence = result["artifacts"]["validated_situation"]["confidence"]
    assert confidence > 0.0, f"expected confidence > 0.0, got {confidence}"


def test_evt_real_001_terminal_type_valid():
    """The run terminates in either an action or an escalation."""
    result = run_pipeline(EventInput(**EVT_REAL_001))
    terminal_type = result["terminal"]["type"]
    assert terminal_type in {"action", "escalation"}, (
        f"expected terminal type action|escalation, got {terminal_type}"
    )


def test_evt_real_001_artifact_chain_has_seven_nodes():
    """The provenance chain preserves the full Event -> Terminal lineage."""
    result = run_pipeline(EventInput(**EVT_REAL_001))
    chain = result["m3_proof"]["provenance_links"]["artifact_chain"]
    assert len(chain) >= 7, f"expected >= 7 chain nodes, got {len(chain)}"