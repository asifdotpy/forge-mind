# ADR-007: Enforce DAG Invariants and Leaf-Worker Constraints

## Status
Amended (2026-08-24) — clause 4 rewritten to match the implemented lineage model. Previously Accepted.

## Context
Unbounded recursive agent spawning can lead to explosive cost loops, non-terminating agent trees, and untraceable failures.

## Decision
Enforce strict topological constraints on the execution tree:
1. Specialist Workers are strict **leaf workers** and have **zero authority to spawn sub-agents**.
2. Execution flows strictly downward along the 5-tier DAG with no cycles.
3. Domain Managers own local retries, timeout boundaries, and error recovery for their partition.
4. **Lineage & trace model**: every derived artifact pins its upstream through schema-required references — `situation_id` as the universal correlation key plus explicit provenance/upstream IDs (`event_id`, `coverage_plan_id`, `evidence_shard_ids`, `finding_ids`, `validated_situation_id`, `decision_id`, `action_id`). The deterministic root trace identifier `execution_trace_id` (`TRC-*`, a pure function of `event_id`) is carried by the artifacts whose contracts define it (currently CoveragePlan and EvidenceShard) and remains derivable anywhere from the event. Parent-child *execution* telemetry is delegated to OpenTelemetry spans mapped onto `execution_trace_id` + `situation_id` (Phase 10 / T1000): trace parenting lives in span context, not duplicated into business payloads.

## Amendment Rationale (2026-08-24)
The superseded clause 4 read verbatim:
> 4. Every artifact must carry full parent-child execution trace identifiers (`execution_trace_id`, `parent_trace_id`).
That wording was never implemented and conflicted with SPEC-001's own data-model ("root trace … where applicable"): only 2 of 9 contracts define `execution_trace_id`, and no contract defines `parent_trace_id`. Cross-artifact causality is instead guaranteed end-to-end by schema-required upstream references (FR-008), asserted at every tier hop by the contract test suite. Duplicating parent pointers into payloads would create a second source of truth beside provenance and would hand-roll what OpenTelemetry span context provides natively. Distributed tracing remains a live requirement, delivered in Phase 10 (OTel → Cloud Trace) rather than as JSON fields.
Notion, the architectural authority, never defined `parent_trace_id`; its ADR-007 requires parent-child trace lineage semantically rather than as payload fields, and its SPEC-001 defines `execution_trace_id` in exactly the CoveragePlan and EvidenceShard contracts — the same two the repository implements. The superseded clause was therefore a repo-local over-specification, and this amendment restores fidelity to the authority rather than relaxing a requirement (independently verified 2026-08-24 against Notion MCP and the ChromaDB Knowledge Brain full-collection scan).

## Alternatives Considered
- Option A: Add `execution_trace_id` (+ `parent_trace_id`) as required fields to all 9 contracts — rejected: touches every schema, fixture pair, derivation path and ~127 tests immediately before the M2 deploy gate; duplicates lineage already encoded in provenance; implements by hand what OTel span context provides. Adding these fields would also move the repository further from, not closer to, the authority's contract spec: 0 of 9 schemas set `additionalProperties: false` — only `event.schema.json` explicitly allows extra properties, the other eight leave the keyword unset — so adding trace fields later remains a purely additive, non-breaking change across all nine contracts. The option is deferred here, not foreclosed.
- Option B: Leave the original clause unamended — rejected: keeps the ADR permanently non-compliant with its own implementation and makes gate reporting rest on a false fulfilment claim.

## Consequences
- **Positive**: Deterministic execution limits, predictable token budgets, robust error isolation; a single source of truth for lineage (provenance) and a single planned mechanism for distributed tracing (OpenTelemetry).
- **Trade-offs**: Complex multi-step tasks must be decomposed into explicit specialist workers rather than dynamic runtime spawning; cross-tier span-level telemetry is deferred until Phase 10.
