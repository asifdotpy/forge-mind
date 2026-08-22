---
description: "Task list for 001-hierarchical-runtime-dag Phase 0 baseline"
---

# Tasks: Hierarchical Engineering Agent Runtime DAG

**Input**: Design documents from `/specs/001-hierarchical-runtime-dag/`

**Prerequisites**: `plan.md` (required), `spec.md` (required for user stories), `research.md`, `data-model.md`, `contracts/`.

**Tests**: Contract + integration tests are REQUIRED by spec.md SC-002/SC-003 (fixture-backed).

**Organization**: Tasks are grouped by Phase 0 baseline (the current scope). Runtime phases (1–6) are future milestones gated by review.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel (different files, no dependencies)
- **Include exact file paths** in each description

## Phase 0 — Repository Skeleton & Spec-Kit Baseline (this milestone)

### S0-Contracts (JSON Schema)

- [ ] T001 [P] Create `specs/001-hierarchical-runtime-dag/contracts/event.schema.json`
- [ ] T002 [P] Create `specs/001-hierarchical-runtime-dag/contracts/coverage-plan.schema.json`
- [ ] T003 [P] Create `specs/001-hierarchical-runtime-dag/contracts/evidence-shard.schema.json`
- [ ] T004 [P] Create `specs/001-hierarchical-runtime-dag/contracts/domain-finding.schema.json`
- [ ] T005 [P] Create `specs/001-hierarchical-runtime-dag/contracts/validated-situation.schema.json`
- [ ] T006 [P] Create `specs/001-hierarchical-runtime-dag/contracts/decision-record.schema.json`
- [ ] T007 [P] Create `specs/001-hierarchical-runtime-dag/contracts/proposed-action.schema.json`
- [ ] T008 [P] Create `specs/001-hierarchical-runtime-dag/contracts/action-validation.schema.json`
- [ ] T009 [P] Create `specs/001-hierarchical-runtime-dag/contracts/escalation.schema.json`

### S1-Fixtures & Scaffolding

- [ ] T010 [P] Create `fixtures/inputs/FIXTURE-001-happy-path.json` (Event envelope + payload)
- [ ] T011 [P] Create `fixtures/inputs/FIXTURE-002-escalation.json` (escalation path)
- [ ] T012 [P] Create `fixtures/expected/FIXTURE-001-expected.json` (assertion set)
- [ ] T013 [P] Create `fixtures/expected/FIXTURE-002-expected.json` (assertion set)
- [ ] T014 [P] Create `src/forgemind/__init__.py` so `import forgemind` succeeds
- [ ] T015 [P] Create `scripts/run_fixture.py` (fixture-backed Phase 0 validator)

### S2-Tests

- [ ] T016 [P] Contract test: validate all fixtures load against all 9 contracts (`tests/contract/test_contracts.py`)
- [ ] T017 [P] Contract test: `pytest tests/contract/` passes 100% (all fixtures → schemas)
- [ ] T018 [P] Integration test: `tests/integration/test_fixture_run.py` asserts happy-path vs expected
- [ ] T019 [P] Integration test: `tests/integration/test_escalation_run.py` asserts escalation path

### S3-Verify & Reconcile

- [ ] T020 Verify `python -c "import forgemind"` succeeds (package importability)
- [ ] T021 [P] Reconcile `docs/specs/SPEC-001.md` to point at `specs/001-hierarchical-runtime-dag/spec.md` (redirect note)
- [ ] T022 Update `docs/CURRENT_STATE.md` to Phase 0 complete (incl. status, next task)
- [ ] T023 [P] Full `pytest tests/` green (brain 5 + secret 6 + new contract/integration)
- [ ] T024 **STOP** — cross-document consistency review (constitution ↔ spec ↔ models ↔ fixtures)

**Checkpoint**: Phase 0 complete — STOP for review before Phase 1.

## Phases 1–6 (gated later — implement after review)

- [ ] T100 Phase 1: Contracts & Event Acquisition (auth, normalization, idempotency, trace IDs)
- [ ] T200 Phase 2: Tier 1 Supervisor (CoveragePlan generation, dispatch)
- [ ] T300 Phase 3: Tier 2 Domain Managers (Code/Delivery/Production)
- [ ] T400 Phase 4: Tier 3 Workers (6 workers; MVP: PR AST + Build Flakiness + Telemetry)
- [ ] T500 Phase 5: Tier 4 Cross-Lifecycle Validator (ValidatedSituation, causality)
- [ ] T600 Phase 6: Tier 5 Reducer + ActionValidation + Escalation (no bypass)

## Dependencies & Execution Order

- **Phase 0**: T001–T024 — this is the current milestone (Set-up/Foundation).
- **Phase 1-6**: depend on Phase 0 gate approval.
- Within Phase 0: contracts (T001–009) → fixtures (T010–015) → tests (T016–019) → verify/reconcile (T020–024).
- Most Phase 0 tasks are `[P]` visible with exact file paths; authoring contracts first unblocks fixtures.

## Implementation Strategy

- Deliver Phase 0 only now (per BUILD-001 Phase 0 gate).
- After review gate passes: build phases incrementally in listed order, running `pytest tests/` after each phase.
- Each user story (US1/US2/US3) maps to phases: US1 → Phase 2 (Supervisor/Coverage), US2 → Phase 3–5, US3 → Phase 6.

## Notes

- [P] tasks target distinct files; no conflicts.
- Re-run ggshield-secure secret scans before any commit (commit only non-secret, intended files).
- Stop at Phase 0 checkpoint to validate baseline independently.