# ADR-003: Adopt a Five-Tier Hierarchical DAG

## Status
Accepted

## Context
Flat multi-agent swarm architectures suffer from uncontrolled circular chatter, non-deterministic execution paths, uncoordinated duplicate tool invocations, and ambiguous decision authority.

## Decision
Replace flat peer-agent coordination with a strict downward Directed Acyclic Graph (DAG):
1. **Tier 1 — Engineering Supervisor**: Global coverage planning and partitioning.
2. **Tier 2 — Domain Managers**: Code Intelligence, Delivery Health, Production Health.
3. **Tier 3 — Specialist Workers**: 6 leaf workers producing focused evidence.
4. **Tier 4 — Cross-Lifecycle Validator**: Evidence reconciliation, causality assessment, situation validation.
5. **Tier 5 — Decision Reducer & Publisher**: Policy evaluation, action proposal, and human escalation.

## Consequences
- **Positive**: Strict execution lineage, deterministic transitions, clear accountability, and inspectable audit trails.
- **Trade-offs**: Requires explicit schema contracts between tiers.
