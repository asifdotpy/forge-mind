# ADR-007: Enforce DAG Invariants and Leaf-Worker Constraints

## Status
Accepted

## Context
Unbounded recursive agent spawning can lead to explosive cost loops, non-terminating agent trees, and untraceable failures.

## Decision
Enforce strict topological constraints on the execution tree:
1. Specialist Workers are strict **leaf workers** and have **zero authority to spawn sub-agents**.
2. Execution flows strictly downward along the 5-tier DAG with no cycles.
3. Domain Managers own local retries, timeout boundaries, and error recovery for their partition.
4. Every artifact must carry full parent-child execution trace identifiers (`execution_trace_id`, `parent_trace_id`).

## Consequences
- **Positive**: Deterministic execution limits, predictable token budgets, robust error isolation.
- **Trade-offs**: Complex multi-step tasks must be decomposed into explicit specialist workers rather than dynamic runtime spawning.
