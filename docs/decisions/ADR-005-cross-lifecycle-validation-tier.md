# ADR-005: Cross-Lifecycle Validation Is a Dedicated Tier

## Status
Accepted

## Context
Individual domain managers only have visibility into their local domain partition (e.g. PR changes or build logs). Merging cross-domain signals prematurely leads to hallucinated causality and false confidence.

## Decision
Establish Tier 4 (Cross-Lifecycle Validator) as the single authoritative stage for multi-domain reconciliation. The validator:
- Correlates findings across Code, Delivery, and Production domains.
- Distinguishes co-occurrence from true causality (`causality_assessment`).
- Flags conflicting or missing evidence (`missing_domains`).
- Emits a unified `ValidatedSituation` payload.

## Consequences
- **Positive**: Prevents ungrounded conclusions from propagating to policy or execution.
- **Trade-offs**: Requires all domain findings to be collected before cross-validation begins.
