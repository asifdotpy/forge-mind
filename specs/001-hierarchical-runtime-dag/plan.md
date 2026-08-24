# Implementation Plan: Hierarchical Engineering Agent Runtime DAG

**Branch**: `001-hierarchical-runtime-dag` | **Date**: 2026-08-22 | **Spec**: `specs/001-hierarchical-runtime-dag/spec.md`

**Input**: Feature specification from `/specs/001-hierarchical-runtime-dag/spec.md`

## Summary

Implement the canonical v3.0 runtime contract for ForgeMind's hierarchical DAG via the Spec-Kit baseline: first establish the repository spec artifacts, contracts, fixtures, and scaffolding (Phase 0), then progress through the Execution Plan/BUILD-001 phases (Contracts & Acquisition → Tier 1 Supervisor → Tier 2 Managers → Tier 3 Workers → Tier 4 Validator → Tier 5 Reducer), ending with Action Validation / Escalation behavior and the Definition-of-Done lineage.

## Technical Context

- **Language/Version**: Python 3.11 (uv-managed)
- **Primary Dependencies**: `jsonschema` (contract validation), `pytest`, `chromadb` (dev-time grounding), `requests`/`httpx` (Notion sync)
- **Storage**: Local fixture files (`fixtures/inputs`, `fixtures/expected`); dev-time knowledge grounding via ChromaDB (Notion sync); durable artifact store deferred (Phase 1+)
- **Testing**: `pytest tests/contract/` (schema), `pytest tests/integration/` (fixture pipeline), fixture runner `scripts/run_fixture.py`
- **Target Platform**: Linux CLI (fixture-backed ingress in Phase 0); Google Cloud (ADK-002) later
- **Project Type**: library + CLI + agent runtime scaffold

## Constitution Check

GATE: Must pass before Phase 0 research; re-check after Phase 1 design.

- Sep-paration of Evidence and Decisions — ✅ (Tier 3 evidence, Tier 5 decision)
- Strict Provenance Trail – ✅ (machine-readable contracts enforce upstream references)
- Causality Rigor — ✅ (`causality_assessment` on ValidatedSituation)
- Visibility of Absence — ✅ (`missing_domains` representation)
- Downstream Action Validation / Escalation — ✅ (ActionValidation contract)

## Project Structure

```text
specs/001-hierarchical-runtime-dag/
├── spec.md              # Feature specification (this feature)
├── research.md          # Phase 0 research (Notion/BUILD-001)
├── data-model.md        # Canonical 9-artifact data model
├── plan.md              # This file
├── tasks.md             # Atomic task checklist
└── contracts/           # JSON Schema (machine-readable)

fixtures/
├── inputs/              # FIXTURE-001-happy-path.json, FIXTURE-002-escalation.json
└── expected/            # expected assertions

src/forgemind/           # Python package (importable)
tests/contract/          # JSON Schema contract tests
tests/integration/       # Integration/stub tests
scripts/run_fixture.py   # Phase 0 fixture runner
```

### Source / Delivery Rationale
- `src/` avoids namespace pollution; `tests/` separated by contract vs integration.
- `fixtures/` at repo root reads naturally with the fixture runner and Spec-Kit policy.

## Complexity Tracking

> Filled ONLY if Constitution Check has violations. None identified — no entry needed.

## Milestones & Phases (per BUILD-001 / Execution Plan)

| Phase | Scope | Exit / Checkpoint |
|-------|-------|-------------------|
| **Phase 0** | Repository skeleton + Spec-Kit baseline; contracts; fixtures; scaffold | Structural contract validity + package importability + cross-doc review; STOP for review |
| **Phase 1** | Contracts & Event Acquisition (event schema, authentication, normalization, idempotency, trace IDs) | One event accepted as a durable, schema-valid artifact |
| **Phase 2** | Tier 1 Supervisor (validate/normalize events, coverage plan, dispatch relevant managers, global constraints) | Trace shows Supervisor → selected Managers + coverage decision |
| **Phase 3** | Tier 2 Domain Managers (Code, Delivery, Production) — bounded dispatch, local retry/timeout | Concurrent manager execution where coverage permits; no cross-domain reconciliation |
| **Phase 4** | Tier 3 Workers (6 workers; MVP vertical slice: PR Pre-Flight AST + Build Log & Flakiness + Telemetry Correlation) | Durable EvidenceShards with provenance; no decisions |
| **Phase 5** | Tier 4 Cross-Lifecycle Validator (gather evidence, coverage, reconcile, dedupe, correlation-vs-causation) | Multi-domain ValidatedSituations reconstructible from provenance |
| **Phase 6** | Tier 5 Decision Reducer + Action Validation + Escalation | No final action bypasses validation; safe action or escalation published |

**Milestones (BUILD-001)**:
- **M1**: FIXTURE-001 passes through the five-tier hierarchy locally.
- **M2**: the same fixture passes through the deployed Google Cloud application.
- **M3**: the judge-visible surface proves provenance, validation, uncertainty, and human control.

### Definition of Done
`Acquire → Analyze → Reconcile → Produce → Validate` completes with visible Supervisor → Manager → Worker → Validator → Reducer lineage, i.e. the canonical object flow `Event → CoveragePlan → Manager/Worker → EvidenceShard → DomainFinding → ValidatedSituation → DecisionRecord → ProposedAction → ActionValidation → Action OR Escalation` runs end to end.

## Execution Order & Dependencies

1. **Phase 0** (this week): contracts → fixtures → tests → package importability → documents → STOP.
2. Phase 1 depends on Phase 0 gate approval.
3. Phases 2–4 sequential (each on validated prior tier).
4. Phases 5–6 depend on 2–4; M1 marks phase completion.
5. M2/M3 are cloud/evaluation milestones after local slice.

**Parallelism**: Phases 3–4 can parallelize within worker/manager pods; Phase 0 tasks marked `[P]` in `tasks.md` are independent.

## Verification Strategy
- `pytest tests/contract/`, `pytest tests/integration/` — automated.
- `python scripts/run_fixture.py fixtures/inputs/FIXTURE-001-happy-path.json` — fixture-backed CLI.
- `python -c "import forgemind"` — package importability.
- `python scripts/query_brain.py --scenario FIXTURE-001` — black-box (post-implementation).