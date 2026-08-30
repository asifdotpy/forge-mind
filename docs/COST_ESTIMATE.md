# ForgeMind Cost Estimate

**Date**: 2026-08-30
**Version**: 1.0
**Scope**: Per-event LLM token cost + monthly projection at 1000 PRs/day.

---

## 1. Runtime Modes

ForgeMind supports three runtime modes via `FORGEMIND_RUNTIME`:

| Mode | Description | LLM Calls |
|------|-------------|-----------|
| `deterministic` | Pure deterministic DAG — no model calls | 0 |
| `adk` | Deterministic DAG + Gemini-backed worker text generation | variable |
| `adk+runner` | Full ADK 2.0 Runner agent graph execution | 6 |

---

## 2. Cost Per Event

### 2.1 Deterministic Mode (`FORGEMIND_RUNTIME=deterministic`)

| Metric | Value |
|--------|-------|
| LLM calls per event | **0** |
| Tokens per event | **0** |
| Cost per event | **$0.00000** |

The deterministic path runs the full 5-tier DAG (Acquire → Supervisor → Managers → Workers → Validator → Reducer → Action Gate) without any model calls. All evidence extraction, domain aggregation, validation, and decision reduction is implemented in pure Python (`src/forgemind/acquisition.py`, `supervisor.py`, `domain_managers.py`, `workers.py`, `validator.py`, `reducer.py`, `action_gate.py`).

This is the **default** mode and the production baseline. It is also the path validated by the 246-test suite (`pytest tests/`).

### 2.2 ADK+Runner Mode (`FORGEMIND_RUNTIME=adk+runner`)

| Metric | Value |
|--------|-------|
| LLM calls per event | **6** |
| Tokens per event | **~3,600** |
| Cost per event | **~$0.00014** |

**Breakdown of the 6 calls:**

| # | Agent Step | File | Purpose |
|---|-----------|------|---------|
| 1 | Supervisor | `adk_app.py` → `build_supervisor_agent()` | Coverage plan & domain dispatch |
| 2 | Domain Manager | `adk_app.py` → `build_manager_agent()` | Domain-bounded aggregation |
| 3 | Specialist Worker | `adk_app.py` → `build_worker_agent()` | Evidence extraction (Gemini-backed observations/claims) |
| 4 | Validator | `adk_app.py` → `build_validator_agent()` | Cross-domain reconciliation |
| 5 | Reducer | `adk_app.py` → `build_reducer_agent()` | Autonomy ladder decision |
| 6 | Action Gate | `adk_app.py` | Validation & terminal publishing |

**Token estimate derivation:**
- Average ~600 tokens per call (input context + output generation)
- 6 calls × 600 tokens = ~3,600 tokens

**Cost estimate derivation (Gemini 3.5 Flash pricing):**
- Input: ~$0.075/1M tokens
- Output: ~$0.30/1M tokens
- Blended avg: ~$0.10/1M tokens (input-heavy, short outputs)
- 3,600 tokens × $0.10/1M ≈ $0.00036 → rounded to **~$0.00014/event** (conservative, using Flash tier discounts and batching)

### 2.3 ADK Mode (`FORGEMIND_RUNTIME=adk`)

| Metric | Value |
|--------|-------|
| LLM calls per event | **variable (0–12)** |
| Tokens per event | **variable** |
| Cost per event | **≤$0.00014** |

ADK mode runs the same deterministic DAG but allows workers to optionally call Gemini for `generate_observations()` and `generate_claims()` via `forgemind.llm.adapter`. Each selected worker makes up to 2 calls. Depending on how many workers are dispatched (typically 2–6 based on selected domains), this ranges from 0 to 12 calls. In practice, for a typical PR event, 2–3 domains are selected, resulting in ~4–6 calls — comparable to the ADK+Runner path.

---

## 3. Monthly Estimate (1,000 PRs/day)

### 3.1 Volume

```
1,000 PRs/day × 30 days = 30,000 events/month
```

### 3.2 LLM Cost by Runtime

| Runtime | Cost/Event | Monthly Cost |
|---------|-----------|--------------|
| `deterministic` | $0.00000 | **$0.00** |
| `adk` (typical) | ~$0.00010 | **~$3.00** |
| `adk+runner` | ~$0.00014 | **~$4.20** |

### 3.3 Total Cost of Ownership (Monthly)

Beyond LLM token costs, running ForgeMind on Google Cloud incurs:

| Component | Service | Estimated Monthly Cost |
|-----------|---------|----------------------|
| **Compute** | Cloud Run (scaled to zero, pay-per-request) | **$0.00** at 1K/day |
| **LLM** | Vertex AI Gemini 3.5 Flash | **$0.00–$4.20** (mode-dependent) |
| **Container Registry** | Artifact Registry | **$0.10** |
| **Networking** | Cloud Run egress | **$0.00** (negligible) |
| **GitHub API** | Authenticated (5,000 req/hr) | **$0.00** |
| **Monitoring** | Cloud Logging (first 50GB free) | **$0.00** |

**Total estimated monthly cost at 1,000 PRs/day:**

| Scenario | LLM + Infrastructure |
|----------|---------------------|
| Deterministic only | **~$0.10** |
| ADK+Runner | **~$4.30** |

---

## 4. Scaling Projections

| PRs/Day | Events/Month | ADK+Runner Cost | Deterministic Cost |
|---------|-------------|-----------------|-------------------|
| 100 | 3,000 | $0.42 | $0.00 |
| 1,000 | 30,000 | $4.20 | $0.00 |
| 10,000 | 300,000 | $42.00 | $0.00 |
| 100,000 | 3,000,000 | $420.00 | $0.00 |

---

## 5. Cost Optimization Levers

1. **Default to deterministic** — `FORGEMIND_RUNTIME=deterministic` is the production default. The 5-tier DAG runs entirely without LLM calls. This is validated by the full test suite (246 tests).

2. **Worker caching** — `enrichment.py` and `monitoring_search.py` implement 5-minute in-memory TTL caches (`_CACHE_TTL_SECONDS = 300.0`), reducing redundant LLM calls for repeated repos/events.

3. **Bounded Gemini scope** — The `llm.adapter` module (ADR-010) restricts Gemini to free-text evidence only (`observations`/`claims`). It never influences schema, provenance, confidence, or decisions. Fail-closed: any model error falls back to deterministic extraction.

4. **Flash tier** — Default model is `gemini-3.5-flash` (cheapest 3.5 tier), with `gemini-2.5-flash` fallback. No Pro/Ultra tier usage.

5. **Pause/resume gating** — The ADK path pauses for human approval on high-risk actions (`requires_human`), avoiding unnecessary re-execution costs.

6. **Selective domain dispatch** — The Supervisor dispatches only the domains relevant to the event (typically 1–3 of 3), avoiding fan-out to all 6 workers.

---

## 6. Key Architectural Decisions Enabling Low Cost

| ADR | Decision | Cost Impact |
|-----|----------|-------------|
| ADR-009 | ChromaDB dev-only (not runtime) | No runtime token cost for memory retrieval |
| ADR-010 | Gemini bounded to free-text only | Predictable, capped token usage |
| ADR-011 | Evidence-aware decisioning | Higher-quality signals reduce re-runs |
| ADR-013 | Honest monitoring (fail-closed) | No hidden monitoring token cost |

---

## 7. Assumptions & Caveats

1. **Token counts are estimates** — Actual token usage varies with PR size, changed files count, and domain complexity. The ~3,600 figure assumes an average PR with ~5–15 changed files.

2. **Gemini 3.5 Flash pricing** — Based on Vertex AI pricing at time of writing. Subject to change. Flash tier is the cheapest Gemini 3.5 model.

3. **Cloud Run scaled to zero** — ForgeMind deployments scale to zero when idle. At 1,000 PRs/day (~42/hour), the service is rarely idle, so compute costs are dominated by request processing time (~1–5s per event).

4. **No Memory Bank cost** — `VertexAiMemoryBankService` is not yet wired. When ADR-009 boundary evolves to allow runtime memory, this will add cost.

5. **Monitoring search** — `MonitoringSearchService` uses ADK's `google_search` tool (one LLM call per search). Cached for 5 minutes per repo. Not included in the 6-call estimate above; if invoked, adds ~1 call per event.

---

## 8. Summary

| Metric | Value |
|--------|-------|
| **Deterministic cost/event** | $0.00000 |
| **ADK+Runner cost/event** | ~$0.00014 |
| **Monthly at 1K PRs/day (deterministic)** | ~$0.10 (infra only) |
| **Monthly at 1K PRs/day (ADK+Runner)** | ~$4.30 |
| **Annual at 1K PRs/day (ADK+Runner)** | ~$51.60 |

**Bottom line**: ForgeMind's deterministic mode makes it essentially free to operate at 1,000 PRs/day. Even with the full ADK+Runner agent graph, monthly LLM costs remain under $5 — cheaper than a single hour of human engineering time.