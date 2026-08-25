# Feature Specification: Hierarchical Engineering Agent Runtime DAG

**Feature Branch**: `001-hierarchical-runtime-dag`

**Created**: 2026-08-22

**Status**: Approved

**Input**: Migrated from `docs/specs/SPEC-001.md` (which itself derives from Notion `BUILD-001` + Notion `SPEC-001`) into the Spec-Kit repository convention.

## Summary

SPEC-001 defines the canonical v3.0 contract for ForgeMind's hierarchical DAG execution lifecycle: `Acquire → Analyze → Reconcile → Produce → Validate`. It standardizes the evidence and decision object flow, the nine canonical artifacts, provenance rules, tier responsibilities, and acceptance criteria so that implementation remains deterministic, inspectable, and review-gated.

Notion remains authoritative for architectural intent, ADRs, and agent profiles. This repository directory (`specs/001-hierarchical-runtime-dag/`) is authoritative for the executable requirements, the machine-readable contracts, the implementation plan (`plan.md`), the task graph (`tasks.md`), and the Phase 0 fixtures.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Route an inbound engineering Event into a coverage plan (Priority: P1)

An engineering signal (PR merged, CI failure, deployment, incident, security alert) arrives as a canonical `Event`. The Tier 1 Engineering Supervisor validates and normalizes the event, determines which lifecycle domains are affected, and emits an explicit `CoveragePlan` that selects bounded Domain Managers without making any downstream engineering decision.

**Why this priority**: MVP depends on deterministic, review-gated ingress before any analysis or decision can occur. This is the foundation of the first executable vertical slice (`Supervisor → Code Intelligence Manager → PR Pre-Flight AST Worker → Cross-Lifecycle Validator → Decision Reducer`).

**Independent Test**: Given `fixtures/inputs/FIXTURE-001-happy-path.json`, running the Phase-0 fixture runner produces a `CoveragePlan` whose `execution_trace_id` / `situation_id` are stable and whose components match `fixtures/expected/`.

**Acceptance Scenarios**:

1. **Given** a canonical happy-path `Event`, **When** the fixture-driven ingress accepts it, **Then** an `Event` artifact is created preserving `situation_id`, `provenance`, and `timestamp`, validated against `contracts/event.schema.json`.
2. **Given** a validated Event, **When** the Supervisor partitions lifecycle domains, **Then** a `CoveragePlan` is emitted listing `selected_domains`, `selected_managers`, rationales, and `execution_trace_id`, validated against `contracts/coverage-plan.schema.json`.

---

### User Story 2 - Evidence to Validated Situation (Priority: P1)

Specialist workers emit bounded `EvidenceShard`s; Domain Managers aggregate them into `DomainFinding`s strictly within their own domain; the Tier-4 Cross-Lifecycle Validator reconciles multi-domain findings into a `ValidatedSituation` — without claiming causation unless clearly evidenced.

**Why this priority**: provenance-preserving evidence and conservative causality are core invariants; everything downstream reads from a `ValidatedSituation`.

**Independent Test**: For each fixture, every derived artifact references its exact upstream IDs and preserves uncertainty, validated against the per-artifact schemas.

**Acceptance Scenarios**:

1. **Given** evidence from multiple domains, **When** the Validator reconciles it, **Then** supporting and conflicting evidence are listed separately and `causality_status` is one of `unsupported|correlated|supported|verified`.
2. **Given** missing domains, **When** the Validator computes coverage, **Then** `coverage` / `missing_domains` are represented explicitly rather than silently omitted.

---

### User Story 3 - Decide, propose, validate, or escalate (Priority: P2)

The Tier-5 Decision Reducer & Publisher evaluates a validated situation against decision policy, emits a `DecisionRecord` and a `ProposedAction`, runs `ActionValidation`, and either publishes a safe action or an `Escalation` requiring a human role.

**Why this priority**: it closes the loop and honors the downstream ActionValidation / Escalation boundary. It depends on US1+US2, so it is P2.

**Independent Test**: `python scripts/run_fixture.py fixtures/inputs/FIXTURE-002-escalation.json` produces an `Escalation` (never an autonomous action).

**Acceptance Scenarios**:

1. **Given** a `ValidatedSituation`, **When** policy is applied, **Then** a `DecisionRecord` references exactly one `validated_situation_id` and carries `autonomy_class`.
2. **Given** a `ProposedAction`, **When** validation fails or confidence/risk requires a human, **Then** the run emits an `Escalation` with `required_human_role`, never an autonomous action.

---

### Edge Cases

- A `CoveragePlan` must never be confusable with a decision artifact.
- Zero-domain or unknown-domain events must produce explicit `missing_domains` in a `ValidatedSituation`, never a silent gap.
- Duplicate / fan-in signals must be deduplicated and correlated without fabricating causation.
- High-uncertainty or insufficiently-supported actions must always produce an `Escalation`.
- A `DecisionRecord` must never reference raw Worker output directly.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST define and validate the canonical `Event` against `contracts/event.schema.json`.
- **FR-002**: System MUST emit a `CoveragePlan` from the Engineering Supervisor before any domain analysis dispatch.
- **FR-003**: Worker Tier (Tier 3) MUST emit only bounded `EvidenceShard`s with source citations.
- **FR-004**: Domain Manager (Tier 2) MUST aggregate evidence only within its own domain.
- **FR-005**: Cross-Lifecycle Validator (Tier 4) MUST produce `ValidatedSituation` and explicitly model coverage gaps.
- **FR-006**: Decision Reducer (Tier 5) MUST consume a `ValidatedSituation` and produce `DecisionRecord` / `ProposedAction`.
- **FR-007**: Action Validation MUST be enforced before any final action or escalation.
- **FR-008**: All derived artifacts MUST maintain provenance/upstream references.
- **FR-009**: Uncertainty MUST remain explicit on every confidence-scored artifact.

### Key Entities

- Event, CoveragePlan, EvidenceShard, DomainFinding, ValidatedSituation, DecisionRecord, ProposedAction, ActionValidation, Escalation

## Canonical Runtime Lifecycle

```plain text
Acquire → Analyze → Reconcile → Produce → Validate
```

## Canonical Object Flow

```plain text
Event
  → CoveragePlan
  → Domain Manager / Specialist Worker execution
  → EvidenceShard
  → DomainFinding
  → ValidatedSituation
  → DecisionRecord
  → ProposedAction
  → ActionValidation
  → Action OR Escalation
```

## Acceptance Criteria

- [ ] Every investigation has one stable `situation_id`.
- [ ] Every derived artifact retains provenance and upstream references.
- [ ] Workers provide bounded evidence and cannot determine final decisions.
- [ ] Domain Managers may aggregate only within their bounded domain.
- [ ] Only the Cross-Lifecycle Validator creates a `ValidatedSituation`.
- [ ] Only the Decision Reducer converts a validated situation into an operational decision.
- [ ] Confidence is not proof; uncertainty remains explicit.
- [ ] Correlation is never represented as confirmed causation without supporting evidence.
- [ ] Every proposed action passes the Action Validation boundary.
- [ ] High-uncertainty or insufficiently supported actions produce escalation.

## Success Criteria

- **SC-001**: `pytest tests/contract/` passes (JSON Schema contract validations).
- **SC-002**: `pytest tests/integration/` passes for the Phase 0 fixture vertical slice.
- **SC-003**: `python scripts/run_fixture.py fixtures/inputs/FIXTURE-001-happy-path.json` exits 0 and matches `fixtures/expected/`.
- **SC-004**: `src/forgemind` is importable (`python -c "import forgemind"`).
- **SC-005**: A cross-document consistency review passes (constitution ↔ spec ↔ data-model ↔ plan ↔ tasks ↔ fixtures).

## Verification Plan

- Automated contract tests: `pytest tests/contract/`
- Integration verification command: `pytest tests/integration/`
- Fixture-backed Phase 0 contracts: `python scripts/run_fixture.py fixtures/inputs/FIXTURE-001-happy-path.json`
- Black-box verification command: `python scripts/query_brain.py --scenario FIXTURE-001`

## Source Alignment

- **Source of truth (intent)**: Notion `BUILD-001`, Notion `SPEC-001`, Notion `Execution Plan`.
- **Repository authority**: `specs/001-hierarchical-runtime-dag/`.
- **Notion authority**: architecture, ADRs, architectural intent, invariants.

## Non-Goals

- Autonomous merge or production deployment.
- Perfect causal inference.
- Production-scale knowledge graph.
- Recursive worker spawning.
- Unbounded peer-to-peer agent communication.

## Required Contract Tests

- valid event creation
- provenance preservation
- evidence-shard validation
- manager aggregation boundaries
- multi-domain validation
- coverage-gap detection
- correlation-vs-causation handling
- decision requires validated situation
- action validation enforcement
- escalation generation
- uncertainty preservation

## Phase 0 Fixture Policy

- `FIXTURE-001`: canonical Event-envelope happy path with separate expected assertions.
- `FIXTURE-002`: canonical Event-envelope escalation path with separate expected assertions.
- Notion `FIXTURE-001 (Change-to-Incident Golden Demo)` is distinct and must not be conflated with Phase 0 repository fixtures.

## Stop Condition

Complete this SPEC-001, the related `data-model.md`, `plan.md`, `tasks.md`, `contracts/`, and repository scaffolding; then stop for review before implementing runtime tiers.