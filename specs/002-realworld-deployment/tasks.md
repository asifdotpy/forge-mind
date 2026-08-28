---
description: "Task list for 002-realworld-deployment — connector layer, CI/CD, Secret Manager, acceptance test"
---

# Tasks: Real-World Deployment Extension (SPEC-002)

**Input**: `specs/002-realworld-deployment/SPEC.md`

**Prerequisites**: SPEC-001 COMPLETE (five-tier DAG, M1/M2/M3 done) · 231 tests green · `deploy/cloudbuild.yaml` + `deploy/deploy.sh` exist.

**Tests**: `tests/acceptance/test_real_value.py` is the SPEC-002 Phase 4 gate (SPEC-002 §5).

**Organization**: Phases are gated and sequential per SPEC-002 §8. Each phase is verified before the next starts.

## Phase 0 — Deployment (M2) ✅

Core manual deploy capability — the foundation for CI/CD automation.

### P0-Deploy
- [x] T800 Author `deploy/cloudbuild.yaml` (BuildKit, image build + push to Artifact Registry)
- [x] T801 Author `deploy/deploy.sh` (COMMIT_SHA substitution, deploy to Cloud Run)
- [x] T802 Manual deploy verified: `forgemind-v3-prod` (us-central1) returns evidence for self-contained event
- [x] T803 Health endpoint ok; FIXTURE-001 passes through deployed `/api/v1/events`

**Checkpoint**: Phase 0 COMPLETE — live endpoint returns evidence. M2 DONE (2026-08-25).

## Phase 1 — GitHub Connector 🔲

Normalize the GitHub webhook path and establish the connector pattern.

### P1-Connector foundation
- [ ] T810 Define `Connector` protocol in `src/forgemind/connectors/_registry.py` (interface-only, no deps)
- [ ] T811 Implement `GitHubPRConnector.receive(raw_payload) -> canonical_event` per SPEC-002 §2.3 mapping
- [ ] T812 Wire `/api/v1/adk/webhook` to use the connector for normalization (refactor existing handler)
- [ ] T813 Add connector isolation test: DAG does not import connector code

**Gate**: Real PR webhook produces a canonical Event that passes through the DAG → evidence_shards >= 1.

## Phase 2 — Cloud Build Trigger 🔲

Automate deploy on push to `main` with a hardened smoke-test gate.

### P2-CI/CD pipeline
- [ ] T820 Configure Cloud Build GitHub trigger on `github.com/asifdotpy/forge-mind` (push to `main`)
- [ ] T821 Extend `deploy/cloudbuild.yaml` with smoke-test stage (run `tests/acceptance/test_real_value.py` against deployed endpoint)
- [ ] T822 Add traffic-migration step: 0% → 100% on smoke pass, scale to 0 on failure
- [ ] T823 Add rollback step: scale previous revision to zero after successful migration
- [ ] T824 Substitution variables: `_REGION`, `_AR_REPO`, `_SERVICE`, `_COMMIT_SHA`

**Gate**: Push to `main` → auto deploy → smoke test passes → traffic migrated.

## Phase 3 — Secret Manager 🔲

Move all secrets out of repo/trigger into Secret Manager.

### P3-Secrets
- [ ] T830 Create Secret Manager secrets: `github-webhook-secret`, `vertex-api-key`
- [ ] T831 Update `deploy/deploy.sh` to inject secrets via `--update-secrets`
- [ ] T832 Remove any plaintext secret references from `cloudbuild.yaml` and trigger config
- [ ] T833 Add test: no plaintext secrets in repo (extend `test_secret_handling.py`)

**Gate**: No plaintext secrets in repo, trigger config, or substitution variables.

## Phase 4 — Acceptance Test 🔲

The SPEC-002 §5 hardened acceptance test — the CI smoke-test gate.

### P4-Acceptance
- [x] T840 Create `tests/acceptance/__init__.py` (package marker)
- [x] T841 Author `tests/acceptance/test_real_value.py` with canonical `EVT-REAL-001` payload
- [x] T842 Assert: evidence_shards >= 1
- [x] T843 Assert: domain_findings >= 1
- [x] T844 Assert: validated_situation.confidence > 0.0
- [x] T845 Assert: terminal.type in {action, escalation}
- [x] T846 Assert: m3_proof.provenance_links.artifact_chain >= 7 nodes
- [x] T847 All 5 acceptance tests pass (verified 2026-08-28)

**Checkpoint**: Phase 4 COMPLETE — acceptance test exists and passes. Gate satisfied.

## Phase 5 — Demo/Submission ✅

Live demo and Devpost submission artifacts.

### P5-Submission
- [x] T850 Live demo verified: Cloud Run endpoint + Vertex AI logs + unedited run + `pytest` green
- [x] T851 Demo script in `SUBMISSION/DEMO_SCRIPT.md`
- [x] T852 Writeup in `SUBMISSION/WRITEUP.md`
- [x] T853 Architecture diagram in `SUBMISSION/ARCHITECTURE.md`
- [x] T854 Spin-up guide in `SUBMISSION/SPINUP.md`

**Checkpoint**: Phase 5 COMPLETE — submission artifacts ready.

## Dependencies & Execution Order

- **Phase 0** → **Phase 1-4** (Phase 0 is prerequisite for all)
- **Phase 1** (connector) and **Phase 4** (acceptance test) are independent — can run in parallel
- **Phase 2** (CI/CD) depends on **Phase 4** (acceptance test is the smoke gate)
- **Phase 3** (secrets) depends on **Phase 2** (CI/CD must exist to wire secrets into)
- **Phase 5** (demo) depends on **Phase 0** + any connector work for live webhook demo

## Implementation Strategy

1. Phase 0 is already COMPLETE (M2 done).
2. Phase 4 (acceptance test) is COMPLETE — the Phase 4 gate is satisfied.
3. Remaining work: Phase 1 (connector) → Phase 2 (CI/CD) → Phase 3 (secrets).
4. Each phase gets its own commit(s), pushed to `origin/main`.
5. Re-run `pytest tests/` after each phase to guard the 231-test baseline.

## Notes

- Phases follow SPEC-002 §8 gated sequence. No phase assumes prior success.
- The acceptance test (`tests/acceptance/test_real_value.py`) is the primary verification artifact — it is deterministic, requires no credentials, and runs in CI.
- Connector isolation and DAG purity invariants (SPEC-002 §6) must be preserved.