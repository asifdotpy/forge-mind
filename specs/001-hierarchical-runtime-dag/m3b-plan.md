# M3-B Implementation Plan — Real Gemini 3.5 via Vertex AI in bounded ADK 2 nodes (code-ready for Cline)

Execution spec for M3-B (T730, T731, T732, T733). Authoritative companion to
**ADR-010** (scope decision) and `m3a-plan.md` (M3-A, already shipped).
READ THIS FILE IN FULL before writing any code. All field names below are
grep-verified against the current codebase.

Repo root (absolute): `/home/asif1/forge-mind`
Python/tooling: use `.venv` (`.venv/bin/python`, `.venv/bin/pytest`). Do NOT
create a venv or run `pip install`/`uv add` without first confirming with the
caller — dependency changes need review (see T730 step 0).

---

## Verified facts (do not re-derive; these constrain the design)

- Runtime has **zero** GCP/ADK/GenAI imports today (grep-confirmed). The only
  `llm` token in `src/` is a docstring word at `acquisition.py:295`.
- `EvidenceShard` contract (`contracts/evidence-shard.schema.json`) has **NO
  `narrative` field**. It carries `observations` and `claims` — both
  `array<string>`. ADR-010's "Gemini produces the shard narrative" therefore
  means: **the model fills `observations`/`claims` string content**, contract
  unchanged. Do NOT add a schema field.
- `Worker` is an ABC (`workers.py:91`) with override points `_observations()`,
  `_claims()`, `_uncertainties()`, `_emit()`, and a single emission path
  `build_shard()` (`workers.py:141`) which validates against the schema.
  `PRPreFlightASTWorker` (`workers.py:307`, key `pr-pre-flight-ast-worker`) is
  the code-intelligence worker named in ADR-010.
- `pyproject.toml` runtime `dependencies` = requests, jsonschema, fastapi,
  uvicorn. ADR-009 kept ChromaDB dev-only; the boundary test
  (`tests/contract/test_runtime_boundary.py:96` `MODULES` list) hard-codes the
  import surface and MUST be extended (not weakened) to include any new module.
- The 133-test suite is deterministic and offline. **No test may assert model
  text.** Gemini is additive; fixtures remain contract-truth.

---

## T730 — ADK 2 orchestration scaffold + `llm/` adapter (deterministic fallback)

**Goal:** wrap the existing five-tier pipeline in an ADK 2 workflow graph
(deterministic stage transitions, pause/resume capable) AND introduce a single
`llm` adapter module that degrades to the current deterministic behavior when
no Vertex credentials are configured. This is the foundation T731/T732 build on.

**Step 0 — dependency decision (RESOLVED via hackathon rules):** ADR-010 names
"Gemini 3.5 via Vertex AI". Per the All Things Agentic Hackathon rules
(allthingsagentichackathon.devpost.com, deadline 2026-08-31), every project
must use (1) Gemini 3.5+ via Gemini API **or** Vertex AI, (2) at least one
Google Agent Framework (ADK, **GenAI SDK**, Antigravity, or GenKit), and (3)
at least one GCP infra service (Cloud Run ✅ already used in M2).
**Chosen client: `google-genai` (the GenAI SDK)** — it is itself an accepted
agent framework credential AND the simplest path to Gemini 3.5 Flash; ADK 2
(ADR-008) remains the chosen workflow framework, and Cloud Run the infra
credential. This combination satisfies all three mandatory requirements with
minimal friction. Add `google-genai` to `[project].dependencies` (NOT dev).
Run `.venv/bin/uv pip install google-genai` to make local imports work; record
the pin in `uv.lock`.

**Step 1 — `src/forgemind/llm/__init__.py` + `src/forgemind/llm/adapter.py`:**
implement a single function
`generate_observations(domain: str, context: dict, *, model: str = "gemini-3.5-flash") -> list[str]`
with this contract:
  - If env `VERTEX_PROJECT` (or `GOOGLE_CLOUD_PROJECT`) AND `GOOGLE_API_KEY` (or
    ADC via `gcloud auth application-default login`) are present → call Vertex
    Gemini, return a list of 1–N observation strings derived from `context`.
  - ELSE (no creds) → return `None` (sentinel) so the caller falls back to the
    existing deterministic `_observations()`.
  - Guard ALL Gemini calls in try/except; on ANY failure return `None`
    (fail-closed to deterministic, never raise into the pipeline).
  - The adapter must import `google.genai` lazily INSIDE the function, so the
    module imports fine even when the package is absent (keeps `import forgemind`
    working offline and the ADR-009 import test green without the dep).
  - No model output is ever treated as schema-authoritative; it only becomes
    `observations`/`claims` text.

**Step 2 — `src/forgemind/adk_runtime.py`:** build an ADK 2 workflow that
reproduces `api.run_pipeline` as a state graph:
  - Nodes: `acquire → supervisor → workers → managers → validator → reducer →
    action_gate`. Each node calls the EXISTING tier functions (no reimplementation).
  - Use ADK `Sequential/Parallel` flow or `Workflow` so stages are explicit and
    pause/resume-capable. The orchestration is deterministic; only the worker
    node's observation source is model-backed (T731).
  - Expose `run_adk_pipeline(body) -> dict` returning the same shape as
    `api.run_pipeline` (so `m3_proof` and the API layer are unchanged).
  - Keep `api.run_pipeline` as the default; add `adk_runtime.run_adk_pipeline`
    as the ADK-backed path. Wire `POST /api/v1/events` to use the ADK path only
    when an env flag `FORGEMIND_RUNTIME=adk` is set; default `deterministic`
    keeps current behavior and all 133 tests green.

**Step 3 — extend ADR-009 boundary test:** add `"forgemind.llm"` and
`"forgemind.adk_runtime"` to the `MODULES` list in
`tests/contract/test_runtime_boundary.py` (around line 96). The ChromaDB
blocker sub-test must STILL pass — `llm`/`adk_runtime` must not import
`chromadb`. Add one new test `test_llm_module_does_not_import_chroma()` and one
`test_adk_runtime_imports_with_chroma_blocked()` mirroring the existing pattern.

**Acceptance (T730):**
- `import forgemind`, `import forgemind.llm`, `import forgemind.adk_runtime`
  succeed with NO Vertex package installed (lazy import holds).
- With `FORGEMIND_RUNTIME=deterministic` (default): `pytest tests/` → 133 passed
  (unchanged baseline).
- With `FORGEMIND_RUNTIME=adk` and NO creds: pipeline still runs (deterministic
  fallback in the adapter); same 133 passed.
- ADR-009 boundary test extended and passing; ChromaDB still absent at runtime.

---

## T731 — Bounded Gemini node for the code-intelligence worker

**Goal:** `PRPreFlightASTWorker` produces model-backed `observations`/`claims`
when Vertex is configured, falling back to deterministic extraction otherwise.
No other worker changes. Contract unchanged.

**Step 1 — `src/forgemind/workers.py`:** modify `PRPreFlightASTWorker` only:
  - In `_observations(self, context)`, first call
    `forgemind.llm.adapter.generate_observations("code", context)`. If it
    returns a non-`None` list → use it (optionally merge with deterministic
    `claims` for citations). If `None` → return the existing deterministic list
    (current `_observations` body, unchanged).
  - Same pattern for `_claims()` if appropriate; keep `confidence`,
    `uncertainties`, `provenance`, `execution_trace_id` EXACTLY as the
    deterministic path produces them — the model must NOT alter schema or
    provenance fields, only the free-text observation/claim content.
  - Do NOT change `build_shard()`, `_assert_*`, or any other worker. Do NOT
    touch the other 5 workers.

**Step 2 — Gemini prompt discipline (in `llm/adapter.py`):** the prompt must
instruct the model to return structured engineering observations derived from
`context.inputs` (changed_files, ci_outcome, etc.), grounded only in that
context. Return strings only. No tool use, no cross-domain reasoning (the
worker is still bounded to `code`).

**Acceptance (T731):**
- No Vertex creds: `PRPreFlightASTWorker().build_shard(plan, ctx)` returns the
  SAME deterministic shard as before (byte-equivalent for the non-observation
  fields; observations equal the deterministic list). 133 tests still pass.
- With creds (caller may supply a fake/local key for a smoke test): shard's
  `observations` are model-derived strings, but `domain=="code"`,
  `confidence`, `provenance.execution_trace_id`, and schema validity are
  unchanged. `jsonschema` validation in `build_shard` passes.
- No contract file under `specs/.../contracts/` is modified.

---

## T732 — Human-approval gate node (ADK pause/resume) at the action gate

**Goal:** make human control EXPLICIT and demonstrable in the runtime (not just
the M3-A proof block). For any terminal action whose `risk_level` exceeds the
supervised threshold (`require_human_above_risk_level`, currently `"critical"`
from `acquisition.py:238`), the ADK workflow pauses for human approval before
publishing; the M3-A `human_control_state` already surfaces this.

**Step 1 — `src/forgemind/adk_runtime.py`:** insert a `human_approval` node
between `reducer` and `action_gate` (or as a gate wrapping `action_gate`):
  - If `decision_record.risk_level` (or `proposed_action` status) triggers
    `requires_human` per the existing reducer logic, the workflow enters a
    PAUSED state with a `pending_approval` token; it does NOT call
    `publish_terminal_output` until resumed with an approval decision.
  - On resume-approve → proceed to `publish_terminal_output` (terminal action).
  - On resume-reject → emit `Escalation` (reuse `action_gate` escalation path),
    no action published.
  - Deterministic (non-ADK) path is unaffected; `api.run_pipeline` keeps its
    current behavior.

**Step 2 — API surface:** add `POST /api/v1/approvals/{token}` (or a
query-param resume on `POST /api/v1/events`) so a human can approve/reject the
paused workflow. Keep it minimal; this is a demo affordance, not a full
auth system. Document the endpoint in `api.py` docstring.

**Acceptance (T732):**
- With `FORGEMIND_RUNTIME=deterministic`: behavior identical to today; 133 tests
  pass; no new endpoint needed (or added but inert).
- With `FORGEMIND_RUNTIME=adk` and a `requires_human` scenario (e.g.
  FIXTURE-002): workflow pauses; `human_control_state.state == "human_review"`
  (or `escalated`); publishing requires an explicit approval call; reject path
  yields `Escalation`.
- No tier authority boundary changed: the Reducer still decides; the gate still
  enforces; ADK only adds pause/resume around the existing gate.

---

## T733 — ADK integration tests + M2 re-deploy

**Step 1 — `tests/contract/test_m3b_adk.py`** (NEW):
  - `test_llm_adapter_falls_back_without_creds` — `generate_observations`
    returns `None` when env creds absent; pipeline stays deterministic; 133
    baseline intact.
  - `test_adk_runtime_imports` — `import forgemind.adk_runtime` ok (lazy).
  - `test_adk_deterministic_path_matches` — with `FORGEMIND_RUNTIME=adk` and no
    creds, `run_adk_pipeline` output equals `run_pipeline` output for
    FIXTURE-001 (shape + key ids).
  - `test_human_approval_pauses` — with creds-flag (or a fake approval backend),
    a `requires_human` case pauses and requires approval to publish.
  - `test_no_chroma_in_runtime` — import-time check that `llm`/`adk_runtime`
    never import `chromadb` (mirrors ADR-009).
  - NONE of these assert specific model text.

**Step 2 — boundary test update** (already in T730 step 3) merged here for the
final green run.

**Step 3 — M2 re-deploy (GATED, caller-authorised):** only after T730–T733
green locally:
  - Update `deploy/cloudbuild.yaml` + `deploy/deploy.sh` to install
    `google-genai` in the image (it is now a runtime dep).
  - Configure Vertex creds via **Secret Manager / Workload Identity** in
    `forgemind-v3-prod` (us-central1) — NEVER a committed key. Reuse the
    existing GCP project `235225823709`.
  - Redeploy to Cloud Run; run FIXTURE-001 through `/api/v1/events`; confirm
    `m3_proof` present and (with creds) Gemini-backed observations appear.
  - Scale to zero after the demo run (cost control, as done for M2).
  - Update `docs/CURRENT_STATE.md` + `README.md` status line (128→133 tests,
    M3 COMPLETE, ADK-001/008 now fulfilled).

**Acceptance (T733):**
- `pytest tests/` → 133 + (new M3-B tests) passed; 133 baseline unchanged in
  behavior.
- ADR-009 boundary test still green (ChromaDB dev-only, absent at runtime).
- M2 re-deploy succeeds only with caller authorisation; live endpoint verified
  then scaled to zero.

---

## Hackathon alignment note (All Things Agentic Hackathon, deadline 2026-08-31)

- ForgeMind is a textbook fit for the **Fortified Enterprise Fleet** track:
  its required capabilities (Agent Registry, Agent Runtime, Memory Bank, Agent
  Identity, Agent Gateway, **Model Armor** guardrails, Agent Observability via
  OpenTelemetry) map directly to ADR-001's GEAP mapping.
- **Mandatory credentials we already satisfy or will:** Gemini 3.5 via Vertex
  AI (T731), Google ADK framework (T730 ADK scaffold), GenAI SDK
  (`google-genai`, T730), Cloud Run infra (M2). All three requirement classes
  covered.
- **Known gap vs the track's full ask:** the track wants persistent cross-session
  "Memory Bank" over weeks — that is exactly what **ADR-009 deferred to
  post-M3** (runtime memory). Not blocking for M3, but a judge may probe it;
  record as a post-M3 backlog item, not in M3-B scope.
- **Submission must include:** live demo on Google Cloud (Cloud Run ✅, scaled
  to zero between demos per cost guidance), architecture diagram, reproducible
  README spin-up instructions, ~4-min demo video. Ensure `docs/CURRENT_STATE.md`
  + README status line reflect M3 COMPLETE and ADK-001/008 fulfilled before
  submitting.

1. **T730** (deps + `llm` adapter + ADK scaffold + boundary-test extension).
2. **T731** (Gemini-backed `PRPreFlightASTWorker`, fallback-safe).
3. **T732** (human-approval pause/resume node + minimal approval endpoint).
4. **T733** (integration tests + M2 re-deploy GATED on authorisation).

Run `pytest tests/` after EACH step. The 133 existing tests MUST stay green at
every step (default `FORGEMIND_RUNTIME=deterministic`). New M3-B tests only
grow the count.

## Hard guardrails (ADR-010 enforcement)
- No tier module's AUTHORITY changes: workers don't decide, validator doesn't
  act, reducer stays sole decision authority, gate still enforces no-bypass.
- Gemini only fills free-text `observations`/`claims`; never schema/provenance
  fields; never a new contract field.
- Fail-closed: any Gemini error → deterministic fallback, never a pipeline
  crash or a forged artifact.
- Credentials NEVER committed; ggshield + `tests/test_secret_handling.py`
  remain authoritative.
- ADR-009 unchanged in spirit: ChromaDB dev-only, absent from runtime image;
  boundary test extended, not weakened.
- No `pip install`/`uv add` without caller review (T730 step 0).

## Definition of Done (M3-B / M3 complete)
- ADK 2 workflow wraps the DAG; Gemini backs one worker's observations with
  deterministic fallback; human-approval pause/resume at the gate.
- `pytest tests/` green (133 baseline + M3-B tests); offline run identical to
  deterministic; ADR-009 boundary intact.
- (Caller-authorised) M2 re-deployed with ADK-enabled image; FIXTURE-001 passes
  through live endpoint; scaled to zero.
- ADR-001/008 marked fulfilled; `CURRENT_STATE.md` + `README.md` updated.
