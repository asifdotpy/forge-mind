# ForgeMind Architecture Specification — Real-World Deployment Extension

**Document type:** Formal architecture specification (extends `docs/ARCHITECTURE.md`)
**Scope:** Connector layer, CI/CD pipeline, environment management, hardened acceptance
**Constraint:** All decisions here extend or instantiate existing ADRs. No ADR is
contradicted. Where this spec introduces new commitments, it does so as a
candidate ADR requiring separate review before implementation.

---

## 1. Architecture Overview (extension)

The existing five-tier DAG (`docs/ARCHITECTURE.md`) is the **core analysis
engine**. This spec adds three surrounding subsystems:

```
                    ┌─────────────────────────────────────────────────────┐
                    │              FORGEMIND PLATFORM                     │
                    │                                                     │
  ┌─────────────┐   │  ┌─────────────────────────────────────────────┐   │
  │  Connector  │──▶│  │         Ingestion API (Cloud Run)           │   │
  │  Layer      │   │  │  POST /api/v1/events  (canonical Event)     │   │
  │  (Cloud     │   │  └──────────────────┬──────────────────────────┘   │
  │  Functions) │   │                     │                              │
  └─────────────┘   │  ┌──────────────────▼──────────────────────────┐   │
                    │  │         Five-Tier Analysis DAG              │   │
  ┌─────────────┐   │  │  Acquire → Workers → Managers → Validator   │   │
  │  CI/CD      │──▶│  │  → Reducer → Gate → Action | Escalation      │   │
  │  Pipeline   │   │  └─────────────────────────────────────────────┘   │
  │  (Cloud     │   │                                                     │
  │  Build)     │   │  ┌─────────────────────────────────────────────┐   │
  └─────────────┘   │  │         Gemini 3.5 (Vertex AI)              │   │
                    │  │  bounded to Tier 3 worker node              │   │
                    │  └─────────────────────────────────────────────┘   │
                    └─────────────────────────────────────────────────────┘
```

### Subsystem responsibilities

| Subsystem | Responsibility | ADR basis |
|---|---|---|
| **Connector Layer** | Normalize vendor webhooks → canonical Event. One connector per source. | ADR-001 "Cloud Run Webhook Receivers" |
| **Ingestion API** | Receive, validate, route canonical Events into the DAG. | ADR-001 "Agent Gateway (GEAP) on Cloud Run" |
| **Five-Tier DAG** | Correlate, validate, decide, act/escalate. | ADR-003..007 |
| **Gemini 3.5** | Bounded reasoning inside Tier 3 worker node. | ADR-001, ADR-008, ADR-010 |
| **CI/CD Pipeline** | Auto build + deploy + smoke test on push to `main`. | extends ADR-002 (single deployable MVP) |
| **Secret Manager** | Store env vars + webhook secrets; inject at deploy time. | extends ADR-001 "Security & Guardrails" |

---

## 2. Connector Layer specification

### 2.1 Connector interface contract

Every connector implements this interface (language-agnostic):

```
interface Connector:
    source_type: string          # "github", "pagerduty", "datadog", ...
    receive(raw_payload) -> canonical_event
    sign_request(event) -> signed_request
    post_to_forgemind(signed_request) -> response
```

### 2.2 Canonical Event contract (from `contracts/event.schema.json`)

```json
{
  "event_id": "EVT-<unique>",
  "situation_id": "SIT-<unique>",
  "timestamp": "<ISO8601>",
  "source": "github|pagerduty|datadog|...",
  "type": "pr|ci_failure|alert|incident|...",
  "summary": "<human-readable>",
  "reference": "<URL or ref>",
  "affected_entities": ["<entity>", ...],
  "provenance": {"source_system": "<vendor>"},
  "payload": { "<vendor-specific>": ... },
  "selected_domains": ["code|delivery|production", ...],
  "selected_workers": ["<worker-name>", ...],
  "require_human_above_risk_level": "critical",
  "max_concurrent_managers": 3,
  "global_timeout_seconds": 300
}
```

### 2.3 First connector: GitHub PR

**Trigger:** GitHub webhook on `pull_request` events.
**Mapping:**

| GitHub field | Canonical Event field |
|---|---|
| `pull_request.id` | `event_id` |
| `pull_request.title` | `summary` |
| `pull_request.html_url` | `reference` |
| `pull_request.changed_files` (via Files API) | `payload.changed_files` |
| `repo.full_name` | `affected_entities[0]` |
| default | `selected_domains: ["code"]` |

**Implementation:** Cloud Function (Python), HTTP trigger, deployed alongside
the Cloud Run service.

### 2.4 Connector registry

Each connector registers itself in a connector catalog
(`src/forgemind/connectors/_registry.py`) so the CI/CD pipeline deploys them
alongside the API. New sources are added by implementing the interface and
registering — no changes to the core DAG.

---

## 3. CI/CD Pipeline specification

### 3.1 Trigger

- Cloud Build GitHub trigger connected to `github.com/asifdotpy/forge-mind`
- Fires on push to `main`
- Substitution variables: `_REGION`, `_AR_REPO`, `_SERVICE`, `COMMIT_SHA`

### 3.2 Pipeline stages (extends existing `deploy/cloudbuild.yaml`)

| Step | Action | Existing/new |
|---|---|---|
| 1 | Build container image (Dockerfile, COMMIT_SHA tag) | existing |
| 2 | Push to Artifact Registry | existing |
| 3 | Deploy to Cloud Run (new revision, 0% traffic) | new |
| 4 | Run smoke test (health + self-contained event → evidence) | new |
| 5 | If smoke test passes → migrate 100% traffic to new revision | new |
| 6 | If smoke test fails → scale new revision to 0 (rollback) | new |
| 7 | Scale previous revision to zero | new |

### 3.3 Smoke test (the "does it actually work" gate)

```bash
curl -s $SERVICE_URL/api/v1/health | grep '"status":"ok"'
curl -s -X POST $SERVICE_URL/api/v1/events \
  -H 'content-type: application/json' \
  -d '{"event":{...schema-valid, no workers key...}}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);assert len(d['artifacts']['evidence_shards'])>=1"
```

This is the hardened acceptance test from §5, run against the live endpoint.

---

## 4. Environment variable specification

### 4.1 Variable inventory

| Variable | Storage | Injected where | Rotation |
|---|---|---|---|
| `FORGEMIND_RUNTIME` | Cloud Build substitution | Cloud Run env | rebuild |
| `VERTEX_PROJECT` | Cloud Run env | Cloud Run env | rebuild |
| `GITHUB_WEBHOOK_SECRET` | Secret Manager `github-webhook-secret:latest` | Cloud Run secret | `--update-secrets` |
| `VERTEX_API_KEY` (if not using ADC) | Secret Manager `vertex-api-key:latest` | Cloud Run secret | `--update-secrets` |

### 4.2 Secret Manager integration

Cloud Build deploy step pulls secrets at deploy time:
```bash
gcloud run deploy $SERVICE \
  --update-secrets=GITHUB_WEBHOOK_SECRET=github-webhook-secret:latest,\
VERTEX_API_KEY=vertex-api-key:latest
```

No key in repo. No key in trigger config. No manual `gcloud run services update`.

---

## 5. Hardened acceptance test specification

### 5.1 Contract

A self-contained event (no `workers` key) with valid schema MUST produce:
- `evidence_shards >= 1`
- `domain_findings >= 1`
- `validated_situation.confidence > 0.0`
- `terminal.type in ("action", "escalation")`
- `m3_proof.provenance_links.artifact_chain` has >= 7 nodes

### 5.2 Test location

`tests/acceptance/test_real_value.py` — a new test suite separate from the
contract/integration suites. Run in CI stage 4 and manually after deploy.

### 5.3 Test payload (canonical example)

```python
{
    "event_id": "EVT-REAL-001",
    "situation_id": "SIT-REAL-001",
    "timestamp": "2026-08-25T10:00:00Z",
    "source": "github",
    "type": "pr",
    "summary": "Refactor auth middleware",
    "reference": "refs/heads/feature/auth",
    "affected_entities": ["auth-service"],
    "provenance": {"source_system": "github"},
    "selected_domains": ["code"],
    "selected_workers": ["pr-pre-flight-ast-worker"],
    "require_human_above_risk_level": "critical",
    "max_concurrent_managers": 3,
    "global_timeout_seconds": 300,
    "payload": {"changed_files": ["auth/middleware.py", "auth/token.py"]},
}
```

---

## 6. Architectural invariants (must hold)

These extend the invariants in `docs/ARCHITECTURE.md`:

1. **Connector isolation:** Connectors MUST NOT contain analysis logic. They
   only normalize → canonical Event → POST. Analysis stays in the DAG.
2. **DAG purity:** The five-tier DAG MUST NOT import connector code. DAG
   depends on the canonical Event schema only.
3. **CI/CD reversibility:** Every deploy MUST be revertible (old revision kept
   until smoke test passes). No destructive deploys.
4. **Secret zero-trust:** Secrets MUST exist in Secret Manager, never in repo,
   trigger config, or substitution variables.
5. **Deterministic fallback:** The Gemini path MUST fail-closed to deterministic
   on any error. No model error reaches the user.

---

## 7. Relationship to existing ADRs

| ADR | How this spec relates |
|---|---|
| ADR-001 | Instantiates "Cloud Run Webhook Receivers" as the Connector Layer |
| ADR-002 | Extends "single deployable MVP" with CI/CD auto-deploy |
| ADR-003..007 | Preserved — no tier authority changes |
| ADR-008 | Preserved — ADK 2 runtime scope unchanged |
| ADR-009 | Preserved — ChromaDB stays dev-only; connectors don't import it |
| ADR-010 | Preserved — Gemini bounded to one worker node |

No ADR is contradicted. The connector interface, CI/CD stages, and secret
management are **candidate commitments** that should be captured as ADR-011,
ADR-012, ADR-013 during implementation.

---

## 8. Execution phases (gated, sequential)

| Phase | What | Gate to next phase |
|---|---|---|
| **0** | Deploy current `f79c17a` manually | Live endpoint returns evidence for self-contained event |
| **1** | GitHub connector (Cloud Function) | Real PR webhook produces evidence |
| **2** | Cloud Build trigger (auto-deploy) | Push to main → auto deploy → smoke test passes |
| **3** | Secret Manager for all secrets | No plaintext secrets in repo/trigger |
| **4** | Hardened acceptance test in CI | CI runs it automatically on every push |
| **5** | Demo video + Devpost submission | Judge can hit the live endpoint |

Each phase is verified before the next starts. No phase assumes prior success.

---

## 9. Out of scope (explicit)

- No new tiers, agents, or databases in the core DAG.
- No ChromaDB in runtime (ADR-009).
- No changes to the five-tier authority boundaries.
- No managed Model Armor service (post-M3 hardening).
- No runtime Memory Bank (ADR-009 deferred).
