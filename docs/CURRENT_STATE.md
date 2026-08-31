# Current State — ForgeMind v3.0

**Date**: 2026-08-30
**Phase**: Phase 4 (SPEC-002) COMPLETE — acceptance test passes; ADR-012 authored; docs/status hygiene done
**Status**: SPEC-001 COMPLETE (M1/M2/M3 done) · SPEC-002 Phase 0 (deploy) + Phase 4 (acceptance test) + Phase 5 (demo) complete; Phase 1–3 in progress (connector/CI/CD/secrets) · 298 passed, 1 skipped (live-token-gated) green (ADK 2.0 Runner tool integration + state-driven pipeline, 2026-08-30; suite count verified 2026-09-01)
**Branch**: `main` → `origin/main` (github.com/asifdotpy/forge-mind, public)

---

## 1. Executive Summary

ForgeMind v3.0 Phase 6 (Tier 5 Decision Reducer + Action Validation + Escalation) is **complete** per `specs/001-hierarchical-runtime-dag/plan.md` Phase 6 exit criteria:

- All 9 canonical JSON Schema contracts authored and validated
- 7 fixture groups with expected assertions authored and passing
- `src/forgemind/` package importable
- `pytest tests/` green (298 passed, 1 skipped — live-token-gated)
- Phase 1 acquisition module (`src/forgemind/acquisition.py`) implements deterministic `Event → CoveragePlan` lineage prefix
- Phase 2 supervisor module (`src/forgemind/supervisor.py`) implements `Event → CoveragePlan → SupervisorDispatch` trace with global constraint enforcement
- Phase 3 domain managers (`src/forgemind/domain_managers.py`) implement bounded-domain aggregation: `Event → CoveragePlan → SupervisorDispatch → DomainFinding`
- Phase 4 workers (`src/forgemind/workers.py`) implement 6 leaf workers producing durable EvidenceShards: `Event → CoveragePlan → SupervisorDispatch → EvidenceShard`
- Phase 5 validator (`src/forgemind/validator.py`) implements cross-domain reconciliation: `DomainFinding(s) → ValidatedSituation`
- Phase 6 reducer (`src/forgemind/reducer.py`) implements the deterministic autonomy ladder: `ValidatedSituation → DecisionRecord → ProposedAction | Escalation`
- Phase 6 gate (`src/forgemind/action_gate.py`) implements ActionValidation enforcement plus `publish_terminal_output()` — the structural no-bypass point for every terminal Action/Escalation
- `specify-cli` 1.0.1 integrated for SDD workflow
- Notion MCP connected (28 tools)
- Knowledge Brain boundary enforced (30 pages, 368 chunks) — **development-time tooling only** per ADR-009

**SPEC-001 Definition-of-Done lineage runs end-to-end locally (M1), through deployed Cloud Run (M2), and the judge-visible surface + Gemini/ADK core (M3) are complete.**

**ADR-009 (2026-08-24)** settles the ChromaDB boundary: ChromaDB provides CONTEXT, not AUTHORITY. It is a development-time derived index over boundary-scoped Notion knowledge, consumed only by SpecForge for planning and verification. It is no longer a runtime dependency, is absent from the production image, and the boundary is enforced by `tests/contract/test_runtime_boundary.py` rather than by documentation alone. Runtime ChromaDB integration is DEFERRED to post-M3.

**ADR-007 amended (2026-08-24)**: clause 4 ("every artifact carries `execution_trace_id` + `parent_trace_id`") was never implemented and conflicted with this data-model; it is rewritten to the implemented lineage model — schema-required upstream provenance on every artifact, deterministic `TRC-*` root trace where contracted (CoveragePlan, EvidenceShard), OpenTelemetry span-based distributed tracing deferred to Phase 10 (T1000). Contracts/code/tests unchanged. Pre-M2 ADR tally: 002–006 + 009 fulfilled · 007 fulfilled-as-amended · 001 & 008 unfulfilled (M2/M3 scope). See FAIL-005.

---

## 2. Repository Status

### 2.1 File System

```
forge-mind/
├── .specify/                          # Spec-Kit project scaffolding
│   ├── constitution.md                # System constitution (Tier boundaries, invariants)
│   ├── feature.json                   # Active feature: specs/001-hierarchical-runtime-dag
│   ├── init-options.json              # Feature numbering: sequential, integration: hermes
│   ├── memory/constitution.md         # Active constitution
│   ├── scripts/bash/                  # 6 shell scripts (check-prerequisites, create-new-feature, etc.)
│   ├── templates/                     # 5 templates (constitution, spec, plan, tasks, checklist)
│   ├── workflows/speckit/workflow.yml # Full SDD Cycle workflow
│   └── integrations/                  # hermes.manifest.json, speckit.manifest.json
├── specs/001-hierarchical-runtime-dag/ # CANONICAL SPEC home
│   ├── spec.md                        # Feature spec (174 lines, 9 FRs, 3 user stories, 5 SCs)
│   ├── research.md                    # Phase 0 research (5 findings, source references)
│   ├── data-model.md                  # 9-artifact data model
│   ├── plan.md                        # Implementation plan (Phases 0-6, M1-M3, DoD)
│   ├── tasks.md                       # T001-T024 (Phase 0) + T100-T600 (gated)
│   └── contracts/                     # 9 JSON Schema (draft-07)
│       ├── event.schema.json
│       ├── coverage-plan.schema.json
│       ├── evidence-shard.schema.json
│       ├── domain-finding.schema.json
│       ├── validated-situation.schema.json
│       ├── decision-record.schema.json
│       ├── proposed-action.schema.json
│       ├── action-validation.schema.json
│       └── escalation.schema.json
├── fixtures/
│   ├── inputs/
│   │   ├── FIXTURE-001-happy-path.json
│   │   ├── FIXTURE-002-escalation.json
│   │   ├── FIXTURE-003-domain-evidence.json # all-3-domain EvidenceShards (drives Tier 2)
│   │   ├── FIXTURE-004-workers.json         # per-worker context (drives Tier 3)
│   │   ├── FIXTURE-005-validator.json       # all-3-domain DomainFindings (drives Tier 4)
│   │   └── FIXTURE-006-decision.json        # verified-causal findings (drives Tier 5 → allowed)
│   └── expected/
│       ├── FIXTURE-001-expected.json
│       ├── FIXTURE-002-expected.json
│       ├── FIXTURE-003-expected.json
│       ├── FIXTURE-004-expected.json
│       ├── FIXTURE-005-expected.json
│       └── FIXTURE-006-expected.json
├── src/forgemind/
│   ├── __init__.py                    # Package exports (paths + all five tiers + gate)
│   ├── _paths.py                      # Canonical path constants
│   ├── acquisition.py                 # Phase 1 event acquisition pipeline
│   ├── supervisor.py                  # Phase 2 Tier 1 supervisor
│   ├── domain_managers.py             # Phase 3 Tier 2 domain managers
│   ├── workers.py                     # Phase 4 Tier 3 specialist workers
│   ├── validator.py                   # Phase 5 Tier 4 cross-lifecycle validator
│   ├── reducer.py                     # Phase 6 Tier 5 decision reducer (autonomy ladder)
│   └── action_gate.py                 # Phase 6 downstream ActionValidation gate + terminal publisher
├── scripts/
│   ├── sync_notion_brain.py           # Notion → ChromaDB sync (with boundary enforcement)
│   ├── query_brain.py                 # ChromaDB semantic query interface
│   ├── run_fixture.py                 # Phase 4 fixture validator (acquisition + CoveragePlan + SupervisorDispatch + DomainFinding + EvidenceShard)
│   └── forgemind_boundary.py          # Boundary definition + enforcement
├── tests/
│   ├── contract/test_contracts.py     # 5 tests
│   ├── contract/test_event_acquisition.py # 19 Phase 1 tests
│   ├── contract/test_supervisor.py    # 18 Phase 2 tests
│   ├── contract/test_domain_managers.py # 15 Phase 3 tests
│   ├── contract/test_workers.py       # 18 Phase 4 tests
│   ├── contract/test_validator.py     # 15 Phase 5 tests
│   ├── contract/test_reducer.py       # 23 Phase 6 tests
│   ├── contract/test_runtime_boundary.py # 4 ADR-009 boundary tests
│   ├── integration/test_fixture_run.py # 4 tests
│   └── test_secret_handling.py        # 6 tests (FAIL-003 regression guard)
├── docs/
│   ├── CURRENT_STATE.md               # This file
│   ├── FAILURE_LOG.md                 # Failure log & institutional memory (FAIL-001..FAIL-005)
│   ├── ARCHITECTURE.md                # v3.0 architecture reference
│   ├── PROJECT.md                     # Project vision
│   └── decisions/                     # ADR-001..ADR-009
├── Dockerfile                         # Cloud Run container image (uv, --no-dev)
├── .dockerignore                      # excludes tests/, deploy/, dev brain scripts
├── deploy/                            # cloudbuild.yaml + deploy.sh (M2)
├── pyproject.toml                     # Python deps + dev groups
└── uv.lock                            # Locked dependencies
```

### 2.2 Git Status

| Status | Value |
|--------|-------|
| Working tree | Clean (all phases + ADR-009 boundary work committed) |
| Branch | `main` tracking `origin/main` |
| Commits | 52 conventional commits; HEAD `6977327` — **0 ahead, synced with `origin/main`** |
| Runtime phase commits | T100 acquisition · T200 supervisor · T300 domain managers · T400 workers · tiers wiring · T500 validator · validator wiring · T600 reducer + action gate · reducer wiring |
| M2 prep commits | `5e807d6` FastAPI + Dockerfile + Cloud Run pipeline · `8e26721` docs/spec alignment · `ea59d55` ADR-009 · `1a66f26` chromadb reclassification · `117272d` Knowledge Brain suite removal · `5afcfb7` GCP deployment env docs · `e4f18f1` ADR amendment |

### 2.3 GitHub Remote (NEW — 2026-08-23)

| Property | Value |
|----------|-------|
| Remote | `origin` → https://github.com/asifdotpy/forge-mind |
| Visibility | PUBLIC (user decision 2026-08-23; ChromaDB brain queried — no prior repo/naming/visibility decision existed) |
| Description | Autonomous engineering control plane: five-tier hierarchical multi-agent DAG following software changes from PR to production (derived from PROJECT.md vision + spec.md summary) |
| Topics | 18 documentation-derived tags (ai-agents, multi-agent-systems, autonomous-agents, hierarchical-agents, dag, llm-agents, engineering-control-plane, spec-driven-development, pr-review, devops, observability, google-adk, vertex-ai, gemini, chromadb, google-cloud, python, json-schema) |
| Settings | Issues enabled · Wiki disabled (docs live in-repo) · delete-branch-on-merge |
| Security | Secret scanning + push protection enabled · Dependabot alerts + automated security fixes enabled (server-side complement to ggshield) |
| License | MIT (`LICENSE`; detected by GitHub) |
| Landing page | Root `README.md` (links PROJECT / ARCHITECTURE / canonical spec / quick start) |
| Method | `gh repo create --public --source --remote=origin --push --description --disable-wiki` → `gh repo edit --add-topic ×18` → hardening via `gh repo edit` + REST API |
| Verification | `gh repo view --json` asserts passed (visibility/description/topics/issues/wiki/license); `git ls-remote` HEAD == local HEAD |

---

## 3. Specification Status (SPEC-001)

### 3.1 Source of Truth

| Layer | Authority | Location |
|-------|-----------|----------|
| Architectural intent | Notion `BUILD-001`, `SPEC-001`, `Execution Plan` | Brain DB (30 pages) |
| Executable specification | `specs/001-hierarchical-runtime-dag/spec.md` | Repository |
| Data contracts | `specs/001-hierarchical-runtime-dag/contracts/*.schema.json` | Repository |
| Implementation plan | `specs/001-hierarchical-runtime-dag/plan.md` | Repository |
| Task graph | `specs/001-hierarchical-runtime-dag/tasks.md` | Repository |

### 3.2 Canonical Artifact Lineage (Frozen in Phase 0)

```
Event → CoveragePlan → EvidenceShard → DomainFinding → ValidatedSituation
      → DecisionRecord → ProposedAction → ActionValidation → Action | Escalation
```

Each artifact has a corresponding JSON Schema in `contracts/`.

### 3.3 Functional Requirements Status

| ID | Requirement | Status | Evidence |
|----|-------------|--------|----------|
| FR-001 | Event validation against schema | PASS | `test_all_fixtures_validate_against_event_schema` + `test_fixture_001_event_is_schema_valid` |
| FR-002 | CoveragePlan emission | PASS | `acquire_event()` emits schema-valid CoveragePlan |
| FR-003 | Bounded EvidenceShard emission | PASS | `workers.py` emits schema-valid EvidenceShards (`test_each_worker_emits_schema_valid_shard`); bounded-domain guard `WorkerError` on cross-domain context |
| FR-004 | Domain-bounded aggregation | PASS | `domain_managers.py` aggregates only within its own domain (`DomainError` on cross-domain evidence; `test_cross_domain_evidence_raises_domain_manager_error`) |
| FR-005 | ValidatedSituation with coverage gaps | PASS | `validator.py` reconciles findings; `missing_domains` explicit (`test_validator.py`, FIXTURE-005) |
| FR-006 | DecisionRecord/ProposedAction | PASS | `reducer.py` autonomy ladder (`DecisionReducer.reduce`; `test_reducer.py` ladder battery, FIXTURE-006) |
| FR-007 | ActionValidation enforcement | PASS | `action_gate.py` gate + `publish_terminal_output()` no-bypass guard (bypass attempts rejected in tests) |
| FR-008 | Provenance/upstream references | PASS | `acquire_event()` preserves provenance + references event_id |
| FR-009 | Explicit uncertainty | PASS | Uncertainties preserved verbatim into DecisionRecord/Escalation (`test_uncertainties_preserved_verbatim_into_record`) |

### 3.4 Success Criteria Status

| ID | Criterion | Status | Evidence |
|----|-----------|--------|----------|
| SC-001 | `pytest tests/contract/` passes | PASS | 117/117 passed (5 baseline + 19 Phase 1 + 18 Phase 2 + 15 Phase 3 + 18 Phase 4 + 15 Phase 5 + 23 Phase 6 + 4 ADR-009 boundary) |
| SC-002 | `pytest tests/integration/` passes | PASS | 4/4 passed |
| SC-003 | Fixture-001 exits 0, matches expected | PASS | `run_fixture.py` → 0 errors |
| SC-004 | `src/forgemind` importable | PASS | `import forgemind` succeeds |
| SC-005 | Cross-document consistency review | PASS | Brain DB queries confirm alignment |

### 3.5 User Stories

| Story | Priority | Status |
|-------|----------|--------|
| US1: Route inbound Event into CoveragePlan | P1 | Phase 2 COMPLETE |
| US2: Evidence to ValidatedSituation | P1 | Phases 3-5 COMPLETE |
| US3: Decide, propose, validate, or escalate | P2 | Phase 6 COMPLETE |

---

## 4. Plan Status (plan.md)

### 4.1 Phase Exit Criteria

| Phase | Scope | Exit Criteria | Status |
|-------|-------|---------------|--------|
| **Phase 0** | Repository skeleton + Spec-Kit baseline | Structural contract validity + package importability + cross-doc review; STOP for review | **COMPLETE** |
| **Phase 1** | Contracts & Event Acquisition | One event accepted as durable, schema-valid artifact | **COMPLETE** (T100) |
| **Phase 2** | Tier 1 Supervisor | Trace shows Supervisor → selected Managers + coverage decision | **COMPLETE** (T200) |
| **Phase 3** | Tier 2 Domain Managers | Concurrent manager execution; no cross-domain reconciliation | **COMPLETE** (T300) |
| **Phase 4** | Tier 3 Workers | Durable EvidenceShards with provenance; no decisions | **COMPLETE** (T400) |
| **Phase 5** | Tier 4 Validator | Multi-domain ValidatedSituations reconstructible | **COMPLETE** (T500) |
| **Phase 6** | Tier 5 Reducer + ActionValidation + Escalation | No final action bypasses validation | **COMPLETE** (T600) — M1 local slice DONE |

### 4.2 Milestones (BUILD-001)

| Milestone | Description | Status |
|-----------|-------------|--------|
| **M1** | FIXTURE-001 passes through five-tier hierarchy locally | **COMPLETE** (2026-08-24) |
| **M2** | FIXTURE-001 passes through deployed Google Cloud application | **COMPLETE** (2026-08-25) |
| **M3** | Judge-visible surface proves provenance, validation, uncertainty, human control | **COMPLETE** (2026-08-25) |

---

## 5. Tasks Status (tasks.md)

### 5.1 Phase 0 Tasks (T001-T024)

| ID | Description | Status |
|----|-------------|--------|
| T001-T009 | Create 9 JSON Schema contracts | COMPLETE |
| T010-T013 | Create fixtures + expected assertions | COMPLETE |
| T014 | Create `src/forgemind/__init__.py` | COMPLETE |
| T015 | Create `scripts/run_fixture.py` | COMPLETE |
| T016-T019 | Contract + integration tests | COMPLETE |
| T020 | Verify package importability | COMPLETE |
| T021 | Reconcile `docs/specs/SPEC-001.md` redirect | COMPLETE |
| T022 | Update `docs/CURRENT_STATE.md` | COMPLETE |
| T023 | Full `pytest tests/` green | COMPLETE (90/90) |
| T024 | STOP — cross-document consistency review | COMPLETE (**PASS** 2026-08-23, dual-verified; report in `specs/001-hierarchical-runtime-dag/reviews/`) |

### 5.2 Future Tasks (Gated)

| ID | Phase | Status |
|----|-------|--------|
| T100 | Phase 1: Contracts & Event Acquisition | **COMPLETE** (2026-08-23) |
| T200 | Phase 2: Tier 1 Supervisor | **COMPLETE** (2026-08-23) |
| T300 | Phase 3: Tier 2 Domain Managers | **COMPLETE** (2026-08-23) |
| T400 | Phase 4: Tier 3 Workers | **COMPLETE** (2026-08-23) |
| T500 | Phase 5: Tier 4 Validator | **COMPLETE** (2026-08-24) |
| T600 | Phase 6: Tier 5 Reducer + ActionValidation + Escalation | **COMPLETE** (2026-08-24) |

---

## 6. Verification Results

### 6.1 Test Suite (latest run — 2026-08-28)

```
$ .venv/bin/python -m pytest tests/ -q
................................................. [ 19%]
..........................................s...... [ 39%]
................................................. [ 59%]
................................................. [ 79%]
................................................. [ 99%]
..                                                [100%]
246 passed, 1 skipped in 30.51s
```

| Suite | Tests |
|-------|-------|
| `tests/contract/test_contracts.py` | 5 |
| `tests/contract/test_event_acquisition.py` | 19 (Phase 1) |
| `tests/contract/test_supervisor.py` | 18 (Phase 2) |
| `tests/contract/test_domain_managers.py` | 15 (Phase 3) |
| `tests/contract/test_workers.py` | 18 (Phase 4) |
| `tests/contract/test_validator.py` | 15 (Phase 5) |
| `tests/contract/test_reducer.py` | 23 (Phase 6) |
| `tests/contract/test_runtime_boundary.py` | 7 (ADR-009 boundary) |
| `tests/contract/test_m3_surface.py` | 6 (M3-A) |
| `tests/contract/test_m3b_adk.py` | 8 (M3-B ADK) |
| `tests/contract/test_evidence_aware_decisioning.py` | 39 (ADR-011) |
| `tests/contract/test_adversarial_evaluation.py` | 14 (ADR-011) |
| `tests/contract/test_payload_enrichment.py` | 10 (ADR-011 Genuine Sources) |
| `tests/acceptance/test_real_value.py` | 5 (SPEC-002 Phase 4) |
| `tests/integration/test_fixture_run.py` | 4 |
| `tests/test_secret_handling.py` | 6 (FAIL-003 guard) |
| `tests/test_env_loader.py` | 8 (dotenv loader) |
| **Total** | **246** |

**Baseline history**: 90 → 128 → 132 → 127 → 141 → 144 → 152 → 191 (+39 ADR-011 evidence-aware) → 231 (+14 adversarial eval + 8 env loader + 18 misc growth) → 236 (+5 acceptance) → 243 (+7 payload enrichment) → 246 (+3 genuine external sources contract tests).

**Every remaining test is independent of the local Knowledge Brain**: the suite runs on a bare clone with no `chromadb` installed and no `NOTION_TOKEN` set.

#### 6.1.1 ADR-009 Boundary Verification (independently reproduced 2026-08-24)

| Check | Command | Result |
|-------|---------|--------|
| Deterministic suite, chromadb import-blocked | `PYTHONPATH=<blocker>:src pytest tests/` | 231 passed, 0 failed |
| Runtime import, chromadb blocked | `python -c "import forgemind"` | OK 0.1.0 |
| chromadb absent from production image | `docker run … python -c "import chromadb"` | `ModuleNotFoundError` |
| runtime importable in production image | `docker run … python -c "import forgemind"` | OK 0.1.0 |
| heavy transitive deps absent from image | `ls site-packages \| grep -iE 'chromadb\|onnxruntime\|tokenizers\|kubernetes'` | NONE PRESENT |
| dev brain scripts absent from image | `docker run … ls scripts/` | only `run_fixture.py`, `forgemind_boundary.py` |
| production image size | `docker images forgemind:adr009` | 347 MB (measured) |
| live container health | `GET /api/v1/health` | `{"status":"ok","service":"forge-mind","version":"0.1.0","phases_complete":6}` |
| live container pipeline | `POST /api/v1/events` (FIXTURE-006) | terminal `action`, `autonomy_class=safe_autonomous`, ActionValidation `allowed` |
| dev Knowledge Brain still usable | `python scripts/query_brain.py "…"` | live semantic matches from the 368-chunk index |

### 6.2 Fixture Runner (latest batch run — all 6 fixtures)

```
$ .venv/bin/python scripts/run_fixture.py
[ok] FIXTURE-001: Supervisor dispatches ['code-intelligence-manager']
[ok] FIXTURE-002: Supervisor dispatches [all 3 managers]
[ok] FIXTURE-002: DecisionRecord DR-2000 reduced to ESCALATION ESC-2000 (reason=coverage_gap)
[ok] FIXTURE-003: DomainFinding FND-3000-{code,delivery,production} aggregate 1 shard(s)
[ok] FIXTURE-004: EvidenceShard ES-4000-{pr-pre-flight-ast,build-log-and-flakiness,telemetry-correlation}-worker emitted
[ok] FIXTURE-005: ValidatedSituation VS-5000-3 reconciles 3 findings (causality_status=correlated)
[ok] FIXTURE-006: DecisionRecord DR-6000 reduced (autonomy_class=safe_autonomous, risk_level=low)
[ok] FIXTURE-006: ActionValidation AV-6000 policy_result=allowed (checks passed: 4/4)
[ok] FIXTURE-006: terminal outcome 'action' published (executed; no-bypass invariant held)

Fixture validation complete. 0 error(s).
```

### 6.3 Tooling Verification

| Tool | Command | Result |
|------|---------|--------|
| specify-cli | `.venv/bin/specify check` | Ready (Hermes Agent available) |
| specify-cli | `.venv/bin/specify integration list` | Hermes installed (default) |
| Notion MCP | `hermes mcp test notion` | Connected, 28 tools |
| Boundary | `.venv/bin/python scripts/forgemind_boundary.py` | 30 pages, enforcement active |
| Brain DB | `.venv/bin/python scripts/query_brain.py "..."` | 368 chunks, semantic search working |

---

## 7. External Integrations

### 7.1 specify-cli 1.0.1

- **Location**: `.venv/bin/specify`
- **pyproject.toml**: `[dependency-groups] dev` only (NOT runtime)
- **Integration**: Hermes Agent (skills-based)
- **Skills at `~/.hermes/skills/`**: speckit-analyze, speckit-checklist, speckit-clarify, speckit-constitution, speckit-converge, speckit-implement, speckit-plan, speckit-specify, speckit-tasks, speckit-taskstoissues
- **Workflow**: speckit (Full SDD Cycle) at `.specify/workflows/speckit/workflow.yml`

### 7.2 Notion MCP

- **Server**: `https://mcp.notion.com/mcp`
- **Auth**: OAuth 2.1 PKCE — **authorized and connected**
- **Tools**: 28 (notion-search, notion-fetch, notion-create-pages, notion-update-page, etc.)
- **Status**: `hermes mcp test notion` → ✓ Connected

### 7.3 Notion Knowledge Brain (development-time only — ADR-009)

- **Role**: derived semantic index over boundary-scoped Notion knowledge, consumed by SpecForge for planning, grounding, consistency review, and cross-session continuity. **CONTEXT, not AUTHORITY** — Notion remains authoritative; on conflict the Truth Hierarchy governs.
- **Classification**: `chromadb` is a `[dependency-groups].dev` dependency. No runtime tier reads from or writes to it; it is absent from the production image.
- **Boundary**: `scripts/forgemind_boundary.py` — 30 pages in scope (stdlib only, no chromadb dependency)
- **Brain DB**: `.brain_db/` (gitignored, 4.7 MB), collection `forgemind_v3_core`, 368 chunks
- **Last sync**: 2026-08-22 (all 30 pages, 4 batches)
- **Query interface**: `scripts/query_brain.py` (semantic search, doc_type/page filters)
- **Tests**: none. The former `tests/test_knowledge_brain.py` asserted the contents of the gitignored local index rather than any code behaviour, so it could not run on another machine or in CI; removed 2026-08-24 (ADR-009 §2). The brain scripts remain as personal development tooling.

### 7.4 GitHub Integration

| Property | Value |
|----------|-------|
| Status | **CONFIGURED** — `origin` → `github.com/asifdotpy/forge-mind.git` (public) |
| Token | N/A (HTTPS with credential helper or SSH) |

---

## 8. Deep Research Summary (Brain DB)

### 8.1 Architecture Queries

| Query | Top Match | Relevance |
|-------|-----------|-----------|
| "ForgeMind v3.0 architecture five-tier DAG" | BUILD-001 Overview (0.62) | High |
| "Phase 0 complete tasks" | SPEC-001 (0.46) | High |
| "PROVENANCE CAUSALITY acceptance criteria" | Engineering Knowledge Model — Provenance Rules (0.49) | High |

### 8.2 Implementation Authority

| Page | ID | Role |
|------|----|------|
| BUILD-001 — ForgeMind MVP Implementation Plan | `3c06566c-d850-8119-a28d-ceb5f8edb008` | Implementation milestones M1-M3 |
| SPEC-001 — Engineering Situation Contract | `3c06566c-d850-810c-b363-d68f5e26cc91` | Canonical artifact contracts |
| Execution Plan | `3bf6566c-d850-81e4-82ad-dadad4861854` | Phase 0-6 execution gates |
| ADK-001 — ADK 2 Workflow Runtime | `3c36566c-d850-8156-bbe4-ebd80f6041d9` | ADK 2 mapping addendum |

### 8.3 Phase 1 Readiness (from brain)

- "Phase 1 event acquisition" matches `Execution Plan → Phase 1 — Contracts and Event Acquisition` (sim 0.50)
- "M1 M2 M3 milestones" matches `BUILD-001 → Milestones` (sim 0.54), `IMP-001 → Deployment Shape` (sim 0.51)
- Brain confirms Phase 1 scope: authentication, normalization, idempotency, trace IDs

---

## 9. Agent Harness (SpecForge Profile)

| Property | Value |
|----------|-------|
| Profile | `specforge` at `~/.hermes/profiles/specforge/` |
| Role | Persistent engineering planner/verifier (not default coding agent) |
| Model | `meituan/longcat-2.0:free` (nous provider) |
| CWD | `/home/asif1/forge-mind` |
| Skills | `project-planning-and-verification`, `spec-driven-planning`, `specify-cli-reference` (at `~/.hermes/profiles/specforge/skills/`) |
| System prompt | `~/.hermes/profiles/specforge/SOUL.md` (architectural invariants, four sources of truth) |
| Memory policy | ForgeMind project-scoped ONLY; no universal Hermes memory for project facts |

---

## 10. Known Issues / Blockers

| Issue | Impact | Resolution |
|-------|--------|------------|
| ~~No remote configured~~ ✅ RESOLVED 2026-08-23 | — | `origin` = github.com/asifdotpy/forge-mind (public, hardened) |
| ~~Runtime tiers NOT implemented~~ ✅ RESOLVED through Tier 5 2026-08-24 | All five tiers shipped (Phases 1–6) | M1/M2/M3 complete — SPEC-001 Definition-of-Done achieved |
| Dependabot: `chromadb` CRITICAL (CVE-2026-45829) | **No longer present in the production image** (ADR-009, verified 2026-08-24: `import chromadb` → `ModuleNotFoundError` inside `forgemind:adr009`) | Reclassified as a dev-only dependency. The earlier FAIL-004 mitigation rested on "embedded client only, no network surface" — a premise that weakened once `5e807d6` shipped an `--allow-unauthenticated` Cloud Run service. The package is now absent from that image rather than merely unreachable within it. Still pinned at 1.5.9 for local dev use only (no fixed release published); keep Chroma in embedded mode, never run a networked Chroma server. |
| Dependabot: `cryptography` HIGH×2/MODERATE | None (mitigated; see FAILURE_LOG FAIL-004) | Accepted with mitigation — ForgeMind code never imports `cryptography`; a `>=49` bump is blocked by `ggshield==1.53.0` (`cryptography<49`). Re-evaluate when ggshield lifts the cap. |
| ForgeMind project-memory | Dev-time grounding via ChromaDB (Notion sync) — CONTEXT, not AUTHORITY (ADR-009) | Runtime memory: DEFERRED to post-M3; requires a new ADR |
| ~~T025 normalization pass outstanding~~ ✅ CLOSED 2026-08-25 (`d951587`) | Contract field-name normalization (W1–W4) was deadlined "before T200" but T200–T600 shipped without it | **CLOSED** — `d951587` (2026-08-25) applied the normalization at the documentation level: constitution §4.2 field renames + §4.3 causality wording, data-model L119, plan.md L26, spec.md L34 backtick, FIXTURE-001 `ingested_at`. W1/W2/W4 prose now matches contracts; W3 (T019 filename) is already correct in `tasks.md` (T018/T019 both cite `tests/integration/test_fixture_run.py`). Docs-only — no code/schema/contract/test changes required (pytest 127/127; `run_fixture.py` 0 errors). Residual: `tasks.md` line 57 `[ ] T025` tracker row not yet flipped |
| ~~T024 cross-document consistency review pending~~ ✅ CLOSED 2026-08-23 | Phase 0 exit | PASS (dual-verified Cline + SpecForge); W1–W5 tracked as T025 normalization |
| ~~ADK Runner async — `run_async()` fails in Cloud Run; workaround called Gemini directly~~ ✅ **RESOLVED 2026-08-27** | `POST /api/v1/adk/events` previously bypassed both the Runner and the hierarchical DAG (a `changed_files`-count confidence heuristic + direct `llm.adapter` calls) so "real" AGENT WASN'T run | **RESOLVED** — `/api/v1/adk/events` now drives the authoritative hierarchical DAG via `forgemind.adk_runtime.run_adk_pipeline` (Acquire → Supervisor → Managers → Workers → Validator → Reducer → human_approval → Action Gate), returning the genuine artifacts + `m3_proof` autonomy signal. The Gemini-direct + heuristic envelope (`analysis`/`actions_taken`) was deleted; Gemini stays bounded in the code worker (`llm.adapter`). Webhook reads the new `autonomy` envelope and now populates `changed_files` from the GitHub API (best-effort). `adk_app` `Runner` kept only as a discovery/session-memory surface. Verified 144/144 + live TestClient (action fixture → `safe_autonomous`/action; escalation fixture → escalation; bare PR event → `paused` human gate). |

---

## 11. Next Actions

| Order | Action | Owner |
|-------|--------|-------|
| 1 | ~~REVIEW GATE~~ ✅ CLOSED 2026-08-23 — T024 PASS (dual-verified: Cline + SpecForge); Phase 0 formally closed; report in `specs/001-hierarchical-runtime-dag/reviews/` | Cline + SpecForge |
| 2 | ~~Commit Phase 0 baseline~~ ✅ DONE 2026-08-23 (5 granular commits, ggshield-gated, pushed to origin) | Cline |
| 3 | ~~Configure GitHub remote and token~~ ✅ DONE 2026-08-23 (public repo asifdotpy/forge-mind) | Cline |
| 4 | ~~Phases 1–4 runtime implementation~~ ✅ DONE 2026-08-23 — T100/T200/T300/T400 complete, 90/90 green, committed & pushed (`02be84a`) | Cline |
| 5 | ~~Phases 5–6 runtime implementation~~ ✅ DONE 2026-08-24 — T500 validator + T600 reducer + action gate complete, 128/128 green, committed & pushed (`e6ac46a`) | Cline |
| 6 | ~~ADR-009 ChromaDB boundary~~ ✅ DONE 2026-08-24 — ADR written, chromadb reclassified as dev-only, boundary machine-enforced (4 tests), Knowledge Brain pseudo-suite removed; 127/127 green; independently verified by SpecForge (Step 10 PASS). 4 commits **awaiting push authorization** | Cline + SpecForge |
| 7 | **Push the 4 pending commits** to `origin/main` | User authorization required |
| 8 | ~~**T025 impact audit**~~ ✅ DONE 2026-08-25 (`d951587`) — audited against `reviews/T024-consistency-review.md` W1–W5: `d951587` normalized W1/W2/W4 prose to contracts (constitution §4.2/§4.3, data-model, plan, spec.md L34, FIXTURE-001 `ingested_at`); W3 already satisfied (`tasks.md` T018/T019 → `tests/integration/test_fixture_run.py`); W5 (missing_domains vocabulary) was a T500 design input, not T025. Docs-only, verified 127/127 + 0 runner errors. **Gate already passed** (row 9). Residual: `tasks.md` L57 `[ ] T025` tracker unflipped | SpecForge |
| 9 | ~~**M2 deployment gate**~~ ✅ COMPLETE 2026-08-25 — T700 deployed forgemind-v3-prod to Cloud Run (us-central1); FIXTURE-001 passes through deployed /api/v1/events; service scaled to zero to preserve credit pool | Cline |
| 10 | ~~**M3** — Judge-visible surface (provenance, validation, uncertainty, human control)~~ ✅ **COMPLETE** (2026-08-25) — M3-A viewer + M3-B Gemini/ADK shipped | Cline |

**Note on M2 readiness**: the ADR-009 gate proved the *development/runtime boundary* holds and that the container runs FIXTURE-006 end-to-end locally. It did **not** establish M2 readiness — M2 requires FIXTURE-001 passing through a *deployed* Google Cloud application. These are distinct claims and are not to be collapsed.

---

## 12. Review Gate Checklist

Per `spec.md` Stop Condition:

- [x] Specification `spec.md` is complete (9 FRs, 3 user stories, 5 SCs, 12 contract tests)
- [x] `data-model.md` defines all 9 canonical artifacts
- [x] `plan.md` defines phases, milestones, DoD
- [x] `tasks.md` defines atomic Phase 0 tasks (T001-T024)
- [x] `contracts/` — all 9 schemas valid (draft-07) *(9/9 SCHEMA-OK, machine-verified 2026-08-23)*
- [x] `fixtures/` — 2 fixtures + expected assertions pass *(runner exit 0, 0 errors)*
- [x] `src/forgemind/` importable
- [x] `pytest tests/` green (20/20 at Phase-0 gate closure; 127/127 as of Phases 1–6 + ADR-009)
- [x] Cross-document consistency review passed (constitution ↔ spec ↔ data-model ↔ plan ↔ tasks ↔ fixtures) — **T024 PASS**, dual-verified (Cline + SpecForge), report: `specs/001-hierarchical-runtime-dag/reviews/T024-consistency-review.md`
- [x] `docs/CURRENT_STATE.md` updated

**All items are COMPLETE. Review gate CLOSED 2026-08-23 (T024 PASS). Phase 1 UNBLOCKED — awaiting user go.**

---

*Generated by SpecForge (specforge profile) — 2026-08-22*  
*Updated: GitHub remote configured & Phase 0 baseline pushed (Cline) — 2026-08-23*  
*Updated: T024 cross-document consistency review PASS — Phase 0 gate CLOSED (Cline + SpecForge dual verification) — 2026-08-23*  
*Updated: Phases 1–4 implemented & verified (T100/T200/T300/T400), 90/90 green, pushed through `02be84a`; body sections refreshed to match (Cline) — 2026-08-23*  
*Updated: Phases 5–6 implemented & verified (T500 validator `4baaafc`; T600 reducer + action gate), 128/128 green, runner 0 errors across 6 fixtures — SPEC-001 M1 local slice COMPLETE (Cline) — 2026-08-24*  
*Updated: ADR-009 ChromaDB boundary accepted — chromadb reclassified as a dev-only dependency, boundary machine-enforced via `tests/contract/test_runtime_boundary.py`, Knowledge Brain pseudo-test suite removed; baseline 127/127; CVE-2026-45829 absent from the production image (verified in-container); FAIL-004 posture corrected. Implemented by Cline, independently verified by SpecForge (Step 10 PASS). 4 commits pending push — 2026-08-24*  
*Updated: ADR-007 amended — trace clause rewritten to match the implemented lineage model (provenance everywhere, `TRC-*` root trace where contracted, OTel span tracing deferred to T1000); FAIL-005 recorded for the overstated audit claim; docs-only change, suite re-verified green — 2026-08-24*

*Updated: T700 (M2) — deployed forgemind-v3-prod to Cloud Run (us-central1), enabled BuildKit in deploy/cloudbuild.yaml (DOCKER_BUILDKIT=1) and granted allUsers run.invoker; health endpoint ok; FIXTURE-001-happy-path.json passes through deployed /api/v1/events (deployed response equivalent to local baseline, M2); service scaled to zero; live image is forgemind:f79c17a (M3 user-value fix) — STALE: does not include d9b3665 dark-theme UI or 6977327 docs rebuild; judges hitting /view/SIT-7000 see the old light-theme viewer — 2026-08-25*  
*Updated: T025 reconciled — `d951587` (2026-08-25) already performed the W1–W4 normalization pass at the documentation level (constitution §4.2/§4.3, data-model, plan, spec.md L34 backtick, FIXTURE-001 `ingested_at`); Verified 127 passed / `run_fixture.py` 0 errors (docs-only). Known Issues & Next Actions rows updated to CLOSED/DONE. Residual: `tasks.md` T025 tracker row still `[ ]` unflipped (SpecForge) — 2026-08-25*

*Refactor: modularised the single-file `src/forgemind/api.py` (1069 LOC) into the `forgemind.api` package — `errors.py` (constants), `models.py` (envelopes), `pipeline.py` (five-tier orchestration, no HTTP), `routes.py` (FastAPI factory + handlers), and a `dashboard/` subpackage (`css|constants|helpers|sections|render`) for the M3-A/T721 read-only judge-visible viewer. Pure code-move: the facade `api/__init__.py` re-exports the identical public surface (`create_api`, `run_pipeline`, `EventInput`, `_render_situation_html`, `app`, …), so `uvicorn forgemind.api:create_api --factory`, the Dockerfile, and existing tests are unchanged. Verified: 141/141 pytest green; rendered viewer byte-identical to the pre-move baseline (16465/15554/15554 chars for the action + escalation fixtures); app boots and `/api/v1/health`, `/view/SIT-7000`, and `POST /api/v1/events` (FIXTURE-007 → terminal action) all pass — 2026-08-27*
*Updated: ADK Runner wiring — `POST /api/v1/adk/events` + `/api/v1/adk/webhook` now execute the authoritative hierarchical ADK DAG (`run_adk_pipeline`) instead of the Google `runner.run_async()` fallback that had reverted to a `changed_files`-count confidence heuristic + direct Gemini calls (see Known Issues row). `AdkEventInput` gained optional `workers`/`evidence_shards`/`domain_findings` (mirrors `EventInput`) to exercise the full autonomy range; new stable `autonomy`/`m3_proof`/`analysis_comment` envelope replaces the old `analysis` heuristic block; the webhook now populates changed files from the GitHub API (best-effort) and reads the new autonomy key. The `google.adk.Runner` / `root_agent` SequentialAgent is now documented as a discovery/session-memory surface, NOT the decision-execution graph. Verified: 144/144 green + live TestClient (action fixture → `safe_autonomous`/action; escalation fixture → escalation; bare GitHub-PR event → `paused` human gate) — 2026-08-27*

*Updated: GitHub webhook action execution — `/api/v1/adk/webhook` now executes exactly the actions the autonomy reducer selected (`_execute_github_actions`, surfaced as `actions_result`): `analysis_comment_posted` fires for both `safe_autonomous` and `human_review` (non-destructive analysis comment; previously only `safe_autonomous`), and `status_check_passed` fires only for `safe_autonomous` (marks the head commit's `forgemind` status success; previously never executed). A missing/invalid `GITHUB_TOKEN` is logged and returned as an error dict instead of silently skipped. `.env.example` documents the minimal single-repo fine-grained token scope (Contents R / Pull requests R / Issues R+W / Commit statuses R+W / Metadata R). Verified: 144/144 pytest green. End-to-end writes still await a real `GITHUB_TOKEN` (user-supplied env / Cloud Run secret) — 2026-08-27*

*Updated: `.env` auto-loading — the API now loads the gitignored project-root `.env` at startup via `forgemind._env.load_dotenv()` wired into `create_api()` (the uvicorn `--factory` target; because the package `__init__` re-exports the factory, any plain `import forgemind` outside pytest applies it too — one-shot per process, mirroring `scripts/sync_notion_brain.py`). Pre-existing env vars always win; the loader is a strict no-op under pytest (suite hermeticity: a dev's real `GITHUB_TOKEN`/`NOTION_TOKEN` can never leak into tests) and in production images (no `.env` file); `FORGEMIND_SKIP_DOTENV=1` opts out; only key NAMES are ever returned/loggable. User's fine-grained single-repo `GITHUB_TOKEN` synced into `.env` (gitignored). Verified: 152/152 pytest green (+8 loader tests in `tests/test_env_loader.py` incl. subprocess-based positive path); live check — token loaded from `.env`, `GET /user` 200 (`asifdotpy`), `GET repos/asifdotpy/script-notes-outline-matrix-agent` 200, authenticated 5000/hr rate tier. Write-path demo (comment + status) now awaits an open PR in the scoped repo — 2026-08-27*

*Updated: paused-projection fix (`5cafb6a`) + LIVE end-to-end demo — paused workflows now surface the reducer's decision (`autonomy_class='human_review'`, `state='human_review_required'`, `actions_taken=['analysis_comment_posted']`) instead of null/'escalated'; `m3_proof` reads top-level `decision_record`/`action_validation` when `terminal` is absent. Cloud Run (`forgemind-v3-prod`, revision `forgemind-00025-wcr`) now runs `FORGEMIND_RUNTIME=adk` (suite verified 152/152 with it — the T905 gate) so `POST /api/v1/approvals/{token}` resumes workflows created by the ADK webhook (previously 404: webhook created pauses unconditionally but resume was runtime-gated). Token rotated to a fine-grained PAT covering `TheVertexAgents/vertex-sentinel`. LIVE verification on real PRs: webhook fires posted genuine ForgeMind analysis comments on #204, #125, #124 (human_review path; no status checks — correct, single-domain evidence stays conservative), approve loop returned 200 with `human_decision=approve` and a published escalation terminal (gate verdict stands by design — post-approval action execution not yet wired). Comment confidence now rounded to 2 decimals. Verified: 152/152 pytest with and without `FORGEMIND_RUNTIME=adk` — 2026-08-28*

*Updated: deploy pipeline fix — `COMMIT_SHA` (Cloud Build built-in) is empty for manual `gcloud builds submit`, which produced an invalid untagged image name (`forgemind:`) and aborted deploys; replaced with a custom `_COMMIT_SHA` substitution (default `manual-build`, overridden by `deploy/deploy.sh` with `git rev-parse --short HEAD`). Final live revision `forgemind-00026-dtf` (image tagged with the real short sha), health ok, live `/adk/events` check confirms rounded confidence rendering — 2026-08-28*

*Updated: Phases 1+2 (docs/status hygiene + SPEC-002 completion) — refreshed CURRENT_STATE.md header to 2026-08-28 and §6.1 test table to 231+1; fixed stale test counts across SUBMISSION/*.md, README.md, docs/PROJECT.md, ADR-011; added ADR-010/011 rows to docs/decisions/README.md; checked off all 10 acceptance criteria in specs/001-hierarchical-runtime-dag/spec.md; flipped T025 tracker in tasks.md; aligned .env.example (FORGEMIND_RUNTIME=adk + FORGEMIND_ADK_MODEL); authored specs/002-realworld-deployment/tasks.md; implemented tests/acceptance/test_real_value.py (5 tests, all passing — SPEC-002 Phase 4 gate satisfied); authored ADR-012-realworld-deployment-surroundings.md (candidate status, honest implemented-vs-deferred table) — 2026-08-28*

*Updated: Webhook Payload Enrichment (ADR-011 Pre-Demo Fix) — authored `src/forgemind/enrichment.py` providing asynchronous, cached payload enrichment from GitHub APIs (PR Files, Check Runs, Commit Statuses). Enriches inbound PR events with `changed_files`, `ci_outcome` ("pass"|"fail"|"unknown"), `docs_summary`, and `dependency_scan` so Tier-3 specialist workers produce real OBSERVED signals (evidence strength 0.67 on clean PRs vs 0.17 previously). Wired `CrossLifecycleValidator().validate(..., repo=repo, sha=sha)` in both `run_adk_pipeline` and `run_pipeline` for independent claim verification; calibrated `BuildLogAndFlakinessWorker` dynamic confidence (0.90 pass / 0.20 fail / 0.50 unknown) and risk levels; verified clean PRs reach `safe_autonomous` and post status checks, while failing CI / missing signals safely fall back to `human_review` / `escalate`. 7 new contract tests added in `tests/contract/test_payload_enrichment.py`. Suite green: 243 passed, 1 skipped — 2026-08-28*

*Updated: Genuine External Evidence Sources (GitHub Advisory API, GitBook API, ADK 2 Search) — eliminated heuristic file matching in payload enrichment. Integrated public GitHub Advisory Database queries (`/advisories`) for modified dependency manifests (`package.json`, `requirements.txt`, `Cargo.toml`, etc.) to produce genuine GHSA vulnerability findings or verified clean audits; integrated live GitBook space querying (`GITBOOK_API_KEY`, `GITBOOK_SPACE_ID`) with honest in-repo docs diff inspection and strict `NO_SIGNAL` fallbacks; integrated ADK 2 search tool for monitoring/incident verification; updated `SecurityAndDependencyWorker` and `AlertStormClusteringWorker` risk/confidence derivation; calibrated `DecisionReducer` evidence-weighted scaling to `(0.85 + 0.15 * evidence_strength)`. 10 contract tests in `tests/contract/test_payload_enrichment.py`. Suite green: 246 passed, 1 skipped — 2026-08-28*

*Updated: Honest Monitoring State (ADR-013) + File-Derived Domain Selection (ADR-014) — closed the two demo-blocking gaps from the honest gap analysis (`/home/asif1/tmp/` audit docs). **ADR-013**: `MonitoringSearchService` now reports a tri-state `state` channel (`"ok"` on any real query, including empty results; `"unavailable"` on ADK-missing/auth/query failure — fail-closed, never fail-open to empty lists); `enrichment.py` forwards `monitoring_state` into payloads; alert/telemetry workers emit `UNAVAILABLE` structured claims when monitoring cannot assess; **fixed `Validator._aggregate_evidence_states` to read the typed `structured_claims` channel** — the string-only fallback never saw the UNAVAILABLE override, so the ADR-013 cannot-assess gate was dead code on the live pipeline (FAIL-006); the reducer's any-`UNAVAILABLE` ⇒ `cannot_assess` ⇒ `human_review` gate is now reachable end-to-end. **ADR-014**: `acquisition.py` derives PR domains from changed files (workflow/CI manifests → delivery, auth/security paths → production, dependency manifests → delivery) instead of the hardcoded `pr → ("code",)`; enrichment keeps every queried channel claimed (ok *or* unavailable) so failures stay visible — reconciliation with ADR-013 documented as an explicit amendment in ADR-014 (FAIL-007); the webhook forwards the derived set instead of hardcoding all three domains. SPEC-001 status unchanged (contracts untouched). Verified: 273 passed, 1 skipped; uvicorn boot with `/` → 200; black-box ALL-PASS — clean+monitored → `safe_autonomous`/action; clean+unmonitored → `human_review`; failing CI → `human_review`; vulnerable dependency → `human_review` — 2026-08-30*


*Updated: Evidence-Derived Confidence + Classifier-Domain Reconciliation (ADR-014 second amendment) — removed the residual `domains.update(("delivery", "production"))` brute-force in `enrichment.py` so `affected_domains` are purely classifier- + evidence-derived (`.github/workflows/ci.yml` -> `["code", "delivery"]`, `README.md` -> `["code"]`, `auth/token.py` -> `["code", "production"]`); kept one narrow queried-channel claim — monitoring `unavailable` still selects `production` so the ADR-013 cannot-assess gate stays reachable from the webhook path (an enrichment outage can never silently *raise* confidence). Made confidence evidence-derived in the three workers pinned at the flat base 0.85: `DocsDriftAndSpecWorker` (0.85 no signal / 0.90 verified clean / 0.70 drift detected), `AlertStormClusteringWorker` (0.0 monitoring-unavailable / 0.90 clean / -0.1 per alert, floor 0.3), `TelemetryCorrelationWorker` (0.0 monitoring-unavailable / 0.90 clean / -0.1 per signal, floor 0.3) — all still honor explicit context-provided confidence. `worker_contexts.build_worker_contexts` now forwards `changed_files` into every worker context that already has its own payload key, so the base file-count confidence heuristic computes meaningful values (workers without their own signal key keep empty inputs — no fabricated contexts). 8 new contract tests (3 confidence, 4 worker-contexts, 1 classifier-domains); offline-fallback test updated to the reconciliation semantics. Verified: 281 passed, 1 skipped; FastAPI app boots; black-box ALL-PASS per plan scenarios — 2026-08-30*

*Updated: ADK 2.0 Runner Tool Integration + State-Driven Pipeline (`adk+runner`) — authored `src/forgemind/tools/adk_tools.py` implementing 6 ADK tool functions (`call_supervisor`, `call_workers`, `call_managers`, `call_validator`, `call_reducer`, `call_action_gate`) adhering to the canonical `tool_context.state` read/write pattern. Connected `call_action_gate` to the shared `_PENDING_APPROVALS` pause/resume store when `requires_human` is emitted. Authored `build_runner_root_agent()` in `agents/root_agent.py` assembling a tool-wired `SequentialAgent` graph with forced single-invocation instructions and `output_key` state emission. Implemented `create_adk_tool_runner()` in `adk_app.py` and `run_adk_runner_pipeline` / `run_adk_runner_pipeline_async` in `adk_runtime.py` with automatic fallback to `run_adk_pipeline`. Configured `POST /api/v1/adk/events` in `adk_routes.py` to route through the runner when `FORGEMIND_RUNTIME=adk+runner`. Documented in `.env.example`. 7 new contract tests in `tests/contract/test_adk_runner.py`. Verified: 288 passed, 1 skipped (0 failures), 0 runner fixture errors across all 6 fixtures — 2026-08-30*



