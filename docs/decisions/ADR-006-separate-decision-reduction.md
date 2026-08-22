# ADR-006: Separate Decision Reduction from Investigation

## Status
Accepted

## Context
Allowing investigative agents to directly execute actions or make policy decisions blurs the boundary between factual discovery and operational authority.

## Decision
Separate investigation from decision-making. Tier 5 (Decision Reducer & Publisher) exclusively evaluates `ValidatedSituation` against enterprise autonomy and risk policies, producing `DecisionRecord`, `ProposedAction`, or `Escalation`.

## Consequences
- **Positive**: Clear auditability; policy rules can be updated without retraining or modifying investigative agents.
- **Trade-offs**: Actions must pass through formal downstream `ActionValidation` before execution.
