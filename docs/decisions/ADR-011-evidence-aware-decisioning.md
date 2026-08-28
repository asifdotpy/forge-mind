# ADR-011: Evidence-Aware Autonomous Decisioning

## Status

Accepted

## Date

2026-08-28

## Problem / Context

ForgeMind's autonomous decisioning system treats "workers looked and found nothing" (NO_SIGNAL) as positive corroboration. In the original implementation, a PR with 5 NO_SIGNAL workers and 1 OBSERVED worker produced confidence 0.75 → `safe_autonomous`. This is not trustworthy — absence of evidence is not evidence of absence.

The system conflated two independent properties:

1. **Confidence** — how certain a worker is in its observation
2. **Evidence quality** — whether the worker actually observed anything

The original architecture allowed high confidence to compensate for missing evidence, enabling "we looked everywhere and found nothing" to be classified as "we confirmed safety."

## Decision

Introduce explicit evidence classification and constrain autonomy based on evidence quality independently from confidence.

### Architecture Rule

> **No confidence score can upgrade an evidence state.**
>
> `NO_SIGNAL + confidence=0.99 ≠ OBSERVED + confidence=0.99`

### Evidence States

Workers emit structured claims with an explicit `evidence_state`:

```python
class EvidenceState(str, Enum):
    OBSERVED = "observed"           # Concrete evidence found
    VERIFIED = "verified"           # Independently confirmed
    NO_SIGNAL = "no_signal"         # Worker looked, found nothing
    UNAVAILABLE = "unavailable"     # Worker could not obtain evidence
    CONTRADICTORY = "contradictory" # Conflicts with another observation
```

### Claim Provenance

Each claim carries a `claim_status` tracking verification level:

```python
class ClaimStatus(str, Enum):
    UNVERIFIED = "unverified"         # Worker claim only
    SUPPORTED = "supported"             # Corroborated by another worker
    INDEPENDENTLY_VERIFIED = "independently_verified"  # Verified against system of record
```

### Evidence Strength as Separate Dimension

The validator computes two independent scores:

- **confidence_score** — weighted average of worker confidences (risk-adaptive)
- **evidence_strength** — ratio of workers with OBSERVED/VERIFIED evidence to total workers

Autonomy requires BOTH to meet thresholds. Neither alone is sufficient.

### Risk-Adaptive Confidence Strategy

| Risk Level | Confidence Strategy |
|------------|---------------------|
| Low        | Evidence-weighted (rewards high evidence strength) |
| Medium     | Conservative weighted (min of boosted and evidence-weighted) |
| High       | Weakest-link (minimum confidence across findings) |
| Critical   | Human approval required (no autonomous action) |

### Action-Risk-Dependent Evidence Threshold

`safe_autonomous` requires sufficient positive evidence across domains **relevant to the proposed action**:

- Post analysis comment: requires code + delivery evidence
- Auto-merge: requires code + delivery + production evidence
- Production remediation: requires all domains

This prevents "winning" the evidence threshold simply by adding more workers.

### Cross-Worker Consistency

The validator checks for contradictions between workers using negation-pair matching. If one worker asserts a claim and another negates it (same canonical key after negation-prefix stripping), the evidence is classified as CONTRADICTORY and autonomy is blocked.

### High/Critical Evidence Override

If ANY worker emits a high/critical risk finding with supporting evidence (not just a risk_level string), autonomous action is forbidden regardless of other workers' confidence. Credible high-risk findings cannot be averaged away.

### Contradictions vs. Coverage Gaps

These are distinct failure modes handled separately:

- **CONTRADICTORY** — two workers emit conflicting claims (detected by negation-pair matching)
- **coverage_gap** — a required evidence source is missing (detected by checking if code reports dependency changes but production domain has no scan evidence)

Both block autonomous action but produce different diagnostic outputs.

## Consequences

### Positive

- The system is significantly harder to fool — "we looked and found nothing" no longer counts as positive evidence
- Autonomy is constrained by evidence quality independently from confidence
- Each decision carries explicit evidence classification, enabling audit
- Cross-worker contradiction detection catches conflicting claims
- High-risk findings cannot be averaged out by confident but irrelevant workers

### Trade-offs / Risks

- **Autonomy rate decreases** — fewer PRs will qualify as `safe_autonomous` because genuine positive evidence is required. This is intentional: the system should be conservative when evidence is weak.
- **NO_SIGNAL detection relies on phrase matching** — the current implementation detects "no signal," "nothing found," "no claim," etc. Workers could emit NO_SIGNAL in a form not matching these phrases. Mitigation: require structured `evidence_state` field on claims rather than parsing claim text.
- **Contradiction detection is limited to negation-pair matching** — subtle contradictions (different metrics, different time windows) are not detected. This is acceptable: the mechanism catches direct contradictions, which is the most important case.
- **Evidence strength denominator includes both domains and workers** — with 3 domains and 6 workers, a single OBSERVED finding produces strength ≈ 0.11, which is below even the low-risk threshold. This means most real-world PRs will be `human_review` unless multiple workers have genuine evidence. This is the intended behavior.

## Verification

- 39 dedicated contract tests in `tests/contract/test_evidence_aware_decisioning.py` cover all evidence-aware mechanisms
- PR #204 (dependabot, 3 files, no CI/security data) now resolves to `human_review` instead of `safe_autonomous` — this is the canonical regression test
- All 191 tests pass (152 original + 39 new)
- Live webhook verification: `selected_domains: ['code', 'delivery', 'production']`, `shards: 6`, `causality: correlated`, `autonomy: human_review`, `actions_taken: ['analysis_comment_posted']`

## Relationship to other ADRs

- Does NOT modify tier authority boundaries (ADR-003/004/005/006/007)
- Extends the Validator's role (ADR-005) with evidence classification
- Extends the Reducer's role (ADR-006) with evidence-aware decisioning
- Does NOT modify the deterministic pipeline — all evidence-aware logic is additive
- Supports ADR-010 (real AI core) by constraining when the system can act autonomously based on AI worker outputs
