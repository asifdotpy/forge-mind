from __future__ import annotations

"""Presentation-only constants for the dashboard (never policy)."""
from forgemind.reducer import AUTONOMOUS_CONFIDENCE, ESCALATE_CONFIDENCE

#: Presentation-only display of the reducer's policy ladder (M3 judge
#: surface): the UI shows WHERE the thresholds sit but never evaluates them.
_GAUGE_ESCALATE_PCT = int(ESCALATE_CONFIDENCE * 100)
_GAUGE_AUTONOMOUS_PCT = int(AUTONOMOUS_CONFIDENCE * 100)

#: Canonical artifact-chain names -> presentation labels.
_ARTIFACT_LABELS = {
    "coverage_plan": "Coverage Plan",
    "evidence_shards": "Evidence Shards",
    "domain_findings": "Domain Findings",
    "validated_situation": "Validated Situation",
    "decision_record": "Decision Record",
    "action_validation": "Action Validation",
    "terminal": "Terminal",
}

#: Short, data-grounded notes for ValidatedSituation.causality_status.
_CAUSALITY_NOTES = {
    "unsupported": (
        "evidence correlates the situation, but causality was not established"
    ),
    "correlated": (
        "signals correlate across domains, but causality is not established"
    ),
    "supported": "causality is supported by the reconciled evidence",
    "verified": "causality is verified by independent corroborating evidence",
}
