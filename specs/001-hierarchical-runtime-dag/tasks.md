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

- [x] T001 [P] Create `specs/001-hierarchical-runtime-dag/contracts/event.schema.json`
- [x] T002 [P] Create `specs/001-hierarchical-runtime-dag/contracts/coverage-plan.schema.json`
- [x] T003 [P] Create `specs/001-hierarchical-runtime-dag/contracts/evidence-shard.schema.json`
- [x] T004 [P] Create `specs/001-hierarchical-runtime-dag/contracts/domain-finding.schema.json`
- [x] T005 [P] Create `specs/001-hierarchical-runtime-dag/contracts/validated-situation.schema.json`
- [x] T006 [P] Create `specs/001-hierarchical-runtime-dag/contracts/decision-record.schema.json`
- [x] T007 [P] Create `specs/001-hierarchical-runtime-dag/contracts/proposed-action.schema.json`
- [x] T008 [P] Create `specs/001-hierarchical-runtime-dag/contracts/action-validation.schema.json`
- [x] T009 [P] Create `specs/001-hierarchical-runtime-dag/contracts/escalation.schema.json`

### S1-Fixtures & Scaffolding

- [x] T010 [P] Create `fixtures/inputs/FIXTURE-001-happy-path.json` (Event envelope + payload)
- [x] T011 [P] Create `fixtures/inputs/FIXTURE-002-escalation.json` (escalation path)
- [x] T012 [P] Create `fixtures/expected/FIXTURE-001-expected.json` (assertion set)
- [x] T013 [P] Create `fixtures/expected/FIXTURE-002-expected.json` (assertion set)
- [x] T014 [P] Create `src/forgemind/__init__.py` so `import forgemind` succeeds
- [x] T015 [P] Create `scripts/run_fixture.py` (fixture-backed Phase 0 validator)

### S2-Tests

- [x] T016 [P] Contract test: validate all fixtures load against all 9 contracts (`tests/contract/test_contracts.py`)
- [x] T017 [P] Contract test: `pytest tests/contract/` passes 100% (all fixtures → schemas)
- [x] T018 [P] Integration test: `tests/integration/test_fixture_run.py` asserts happy-path vs expected
- [x] T019 [P] Integration test: `tests/integration/test_fixture_run.py` asserts escalation path

### S3-Verify & Reconcile

- [x] T020 Verify `python -c "import forgemind"` succeeds (package importability)
- [x] T021 [P] Reconcile `docs/specs/SPEC-001.md` to point at `specs/001-hierarchical-runtime-dag/spec.md` (redirect note)
- [x] T022 Update `docs/CURRENT_STATE.md` to Phase 0 complete (incl. status, next task)
- [x] T023 [P] Full `pytest tests/` green (brain 5 + secret 6 + new contract/integration)
- [x] T024 **STOP** — cross-document consistency review — ✅ **PASS 2026-08-23** (dual-verified: Cline planner + SpecForge verifier · report: `specs/001-hierarchical-runtime-dag/reviews/T024-consistency-review.md` · W1–W5 non-blocking)
- [x] T025 [P] Normalization pass (W1–W4): constitution §4.2 field names → contract names (`evidence_shard_ids`, `finding_ids`, `supporting_evidence`, `conflicting_evidence`, `action_id`, `validated_situation_id`); reword `causality_assessment` → "result recorded in `causality_status`" (data-model L119, plan L26, constitution §4.3); fix spec.md L34 heading backtick; unify fixture provenance key → `ingested_at`; reconcile T019 filename (`test_escalation_run.py` → `test_fixture_run.py`). **DEADLINE: before T200 (Phase 2 code-gen).** [W5 `missing_domains` vocabulary → design input for T500]

**Checkpoint**: Phase 0 complete — review gate **CLOSED 2026-08-23** (T024 PASS). Phase 1 unblocked.

## Phases 1–6 (gated later — implement after review)

- [x] T100 Phase 1: Contracts & Event Acquisition (auth, normalization, idempotency, trace IDs)
- [x] T200 Phase 2: Tier 1 Supervisor (CoveragePlan generation, dispatch)
- [x] T300 Phase 3: Tier 2 Domain Managers (Code/Delivery/Production)
- [x] T400 Phase 4: Tier 3 Workers (6 workers; MVP: PR AST + Build Flakiness + Telemetry)
- [x] T500 Phase 5: Tier 4 Cross-Lifecycle Validator (ValidatedSituation, causality)
- [x] T600 Phase 6: Tier 5 Reducer + ActionValidation + Escalation (no bypass)

**Checkpoint**: Phases 1–6 COMPLETE (2026-08-24). SPEC-001 Definition-of-Done lineage runs end-to-end locally: `Event → CoveragePlan → EvidenceShard → DomainFinding → ValidatedSituation → DecisionRecord → ProposedAction → ActionValidation → Action OR Escalation`. M1 local slice DONE; M2 COMPLETE (2026-08-25); M3 COMPLETE (2026-08-25).

## M3 — Judge-Visible Surface (Milestone 3)

**Status**: COMPLETE (2026-08-25). M1 COMPLETE (2026-08-24); M2 COMPLETE
(2026-08-25); M3 COMPLETE (2026-08-25). The four proof points (provenance,
validation, uncertainty, human control) are shipped: M3-A judge-visible viewer
read-only HTML surface + M3-B Gemini/ADK core (ADR-010). SPEC-001
Definition-of-Done achieved.

### M3-0 — Scope gate (STOP before code)
- [x] T710 **STOP** — M3 AI scope DECIDED (2026-08-25): option (b) real Gemini 3.5 via Vertex AI inside bounded ADK 2 nodes. Recorded in **ADR-010**; M3-B UNBLOCKED.
- [x] T711 Author `FIXTURE-007-m3-judge-surface` (happy-path action + escalation/human-control) + expected assertions.

### M3-A — Judge-visible surface (always required, deterministic)
> Execution spec: `specs/001-hierarchical-runtime-dag/m3a-plan.md` (code-ready, field-verified).
- [x] T720 Add `GET /api/v1/situations/{situation_id}` returning lineage + M3 proof block (`provenance_links`, `validation_verdict`, `uncertainty_summary`, `human_control_state`). Read-only; no tier changes.
- [x] T721 Add read-only HTML situation viewer (`/` or `/view/{id}`): lineage graph, validation badge, uncertainty callouts, escalation/human-role banner.
- [x] T722 M3 surface contract test: four properties derive correctly for FIXTURE-001 (action) and FIXTURE-002 (escalation).

### M3-B — AI core (conditional on T710 = option b)
> Execution spec: `specs/001-hierarchical-runtime-dag/m3b-plan.md` (code-ready, ADR-010-aligned).
- [x] T730 ADK 2 workflow scaffold wrapping the DAG (state graph, pause/resume) per ADR-008 + `llm/` adapter with deterministic fallback.
- [x] T731 Bounded Gemini 3.5 (Vertex AI) node for one worker (e.g. code-intelligence) producing EvidenceShard narrative; contracts unchanged.
- [x] T732 Human-approval gate node (ADK pause/resume) at the action gate.
- [x] T733 ADK integration tests; re-run M2 deploy with ADK-enabled image.

### M3 guardrails
- M3-A is presentation only (reads existing artifacts; no LLM in tiers).
- Under M3-B, Gemini stays bounded inside designated nodes; Validator/Reducer authority boundaries NOT collapsed.
- Sequence M3-0 → M3-A first (shippable deterministic M3); M3-B only after T710.

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