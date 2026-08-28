# ADR-012: Real-World Deployment Surroundings (Connector Layer, CI/CD, Secret Manager)

## Status

Candidate (2026-08-28) — records SPEC-002 commitments; formal acceptance deferred to implementation per SPEC-002 §7.

## Date

2026-08-28

## Context

SPEC-002 (`specs/002-realworld-deployment/SPEC.md`) extends the five-tier DAG with three surrounding subsystems: a connector layer (vendor webhooks → canonical Event), a CI/CD pipeline (auto build + deploy + smoke test on push), and Secret Manager integration (no plaintext secrets in repo/trigger). This ADR captures the SPEC-002 commitments as candidate architectural decisions so they are visible and reviewable before implementation begins.

The connector interface, CI/CD stages, and secret management approach are deliberately recorded as *candidate* commitments per SPEC-002 §7 rules — they require separate ADR review before implementation.

## Decision (candidate)

Adopt the SPEC-002 deployment surroundings as three coordinated subsystems around the existing five-tier DAG.

### 1. Connector Layer

Every vendor source implements a single `Connector` interface:

```
interface Connector:
    source_type: string          # "github", "pagerduty", "datadog", ...
    receive(raw_payload) -> canonical_event
    sign_request(event) -> signed_request
    post_to_forgemind(signed_request) -> response
```

- Connectors MUST NOT contain analysis logic (connector isolation invariant).
- The five-tier DAG MUST NOT import connector code (DAG purity invariant).
- First connector: GitHub PR webhook → canonical Event (EVT-REAL-001 mapping per SPEC-002 §2.3).
- Connectors register themselves in `src/forgemind/connectors/_registry.py` so CI/CD deploys them alongside the API.

### 2. CI/CD Pipeline

Extends existing `deploy/cloudbuild.yaml` with a hardened smoke-test gate:

| Step | Action | Status |
|------|--------|--------|
| 1 | Build container image (Dockerfile, COMMIT_SHA tag) | **existing** (`deploy/cloudbuild.yaml`) |
| 2 | Push to Artifact Registry | **existing** |
| 3 | Deploy to Cloud Run (new revision, 0% traffic) | **new** |
| 4 | Run smoke test (health + self-contained event → evidence) | **new** — runs `tests/acceptance/test_real_value.py` against the deployed endpoint |
| 5 | If smoke passes → migrate 100% traffic | **new** |
| 6 | If smoke fails → scale new revision to 0 (rollback) | **new** |
| 7 | Scale previous revision to zero | **new** |

Every deploy MUST be revertible (CI/CD reversibility invariant). Old revision kept until smoke test passes.

### 3. Secret Manager

All secrets stored in Secret Manager, never in repo, trigger config, or substitution variables:

| Variable | Storage | Injected where |
|----------|---------|----------------|
| `FORGEMIND_RUNTIME` | Cloud Build substitution | Cloud Run env |
| `VERTEX_PROJECT` | Cloud Run env | Cloud Run env |
| `GITHUB_WEBHOOK_SECRET` | Secret Manager `github-webhook-secret:latest` | Cloud Run secret |
| `VERTEX_API_KEY` (if not ADC) | Secret Manager `vertex-api-key:***` | Cloud Run secret |

Cloud Build pulls secrets at deploy time via `--update-secrets`. No key in repo. No key in trigger config. No manual `gcloud run services update`.

## Alternatives Considered

- **Keep manual deploys (status quo)**: Rejected — does not satisfy SPEC-002 Phase 2 gate (push to main → auto deploy → smoke test). Manual deploys are error-prone and unreproducible for judges.
- **Inline secrets in cloudbuild.yaml**: Rejected — violates the secret zero-trust invariant; secrets would be visible in source control history.
- **Connectors with embedded analysis**: Rejected — violates connector isolation; analysis stays in the DAG, connectors only normalize.

## Implemented vs. Deferred

| Commitment | Status | Evidence |
|------------|--------|----------|
| GitHub webhook receiver (`/api/v1/adk/webhook`) | **implemented** | `src/forgemind/api/adk_routes.py` |
| Connector interface | **deferred** | no `src/forgemind/connectors/` package |
| Connector registry | **deferred** | no registry module |
| Cloud Build trigger (auto-deploy) | **deferred** | `deploy/cloudbuild.yaml` exists but lacks smoke-test + traffic migration steps |
| Secret Manager integration | **deferred** | no Secret Manager refs in deploy scripts |
| Acceptance test (`tests/acceptance/test_real_value.py`) | **implemented** | 5 tests, all passing |
| Smoke test in CI | **deferred** | acceptance test exists but is not wired into Cloud Build stage 4 |

## Consequences

### Positive
- SPEC-002 Phase 4 gate now has a concrete test artifact (`tests/acceptance/test_real_value.py`) that can be run locally or in CI.
- Commitments are explicit and reviewable before implementation effort is spent.
- Connector isolation and DAG purity invariants preserve the existing test suite (231 passed) — no risk to the deterministic pipeline.

### Trade-offs / Risks
- **Scope**: implementing all three subsystems is substantial work. Phased approach (connector → CI/CD → secrets) reduces risk but extends timeline.
- **Credential requirements**: the GitHub connector needs a real `GITHUB_TOKEN` and webhook secret for end-to-end verification — these are user-supplied, not available in CI until configured.
- **Status quo is functional**: the manual deploy path already works (M2 complete). The value of auto-deploy is reproducibility and judge-visible CI, not runtime capability.

## Verification

- `tests/acceptance/test_real_value.py` passes 5/5 — the Phase 4 gate is satisfied.
- Existing 231-test suite remains green — no regression from doc/test-only changes.
- SPEC-002 §6 architectural invariants hold:
  - Connector isolation: no connector code exists yet, so invariant trivially holds.
  - DAG purity: no connector imports in `src/forgemind/` (verified: `grep -r connectors src/forgemind/` returns nothing).
  - CI/CD reversibility: existing deploy keeps old revision.
  - Secret zero-trust: `ggshield` + `tests/test_secret_handling.py` guard the repo.
  - Deterministic fallback: `FORGEMIND_RUNTIME=adk` fails closed (verified by `test_llm_adapter_falls_back_without_creds`).

## Relationship to Other ADRs

- **ADR-001**: Instantiates "Cloud Run Webhook Receivers" as the Connector Layer.
- **ADR-002**: Extends "single deployable MVP" with CI/CD auto-deploy.
- **ADR-003..007**: Preserved — no tier authority changes.
- **ADR-008**: Preserved — ADK 2 runtime scope unchanged.
- **ADR-009**: Preserved — ChromaDB stays dev-only; connectors don't import it.
- **ADR-010**: Preserved — Gemini bounded to one worker node.
- **ADR-011**: Preserved — evidence-aware decisioning unaffected by deployment surroundings.

## References

- SPEC-002: `specs/002-realworld-deployment/SPEC.md`
- SPEC-002 §5: hardened acceptance test contract
- SPEC-002 §6: architectural invariants
- SPEC-002 §7: candidate commitment rules
- Existing deploy: `deploy/cloudbuild.yaml`, `deploy/deploy.sh`
- Existing webhook: `src/forgemind/api/adk_routes.py`