# M3-A Implementation Plan — Judge-Visible Surface (code-ready for Cline)

This document is the execution spec for M3-A (T711, T720, T721, T722). It is
deterministic and presentation-only: **no tier logic changes, no new LLM/ADK
dependency, no contract/schema changes**. Every field referenced below is
verified to exist in the current codebase.

Repo root (absolute): `/home/asif1/forge-mind`
Python: run inside `.venv` (`.venv/bin/python`). Tests: `pytest tests/`.

---

## Proven field reference (verified in code)

`src/forgemind/api.py::run_pipeline` returns a dict with:
- `status` ("ok"), `situation_id`, `trace_id` (= `execution_trace_id`),
  `terminal` (dict), `artifacts` (dict).
- `terminal`: `{type, decision_record, proposed_action, action_validation, escalation}`.
- `artifacts`: `{coverage_plan, supervisor_dispatch, evidence_shards, domain_findings, validated_situation}`.

Real field names you MUST use (grep-confirmed):
- `acquisition.CoveragePlan`: `coverage_plan_id`, `situation_id`,
  `provenance.event_id`, `execution_trace_id`.
- `validator.ValidatedSituation`: `causality_status` (correlated|supported|
  verified), `confidence` (float, 0.0–1.0), `coverage.missing_domains` (list),
  `coverage.coverage_percentage` (int), `uncertainties` (list).
- `reducer.DecisionRecord`: `autonomy_class` (safe_autonomous|human_review|
  escalate), `risk_level` (low|medium|high), `uncertainties` (list).
- `action_gate.ActionValidation`: `policy_result` (allowed|requires_human|
  rejected), `reason`, `validation_id`.
- `action_gate.Escalation`: `required_human_role`, `reason`, `evidence_ids`.

---

## T711 — Fixture + expected assertions for M3 proof points

**File to create:** `fixtures/inputs/FIXTURE-007-m3-judge-surface.json`
**File to create:** `fixtures/expected/FIXTURE-007-expected.json`

**Goal:** one fixture that exercises BOTH M3 proof paths in a single run is not
possible (a single event yields one terminal outcome). Instead create TWO
inputs that share the same `fixture_id` prefix `FIXTURE-007`:
- `FIXTURE-007-m3-judge-surface-action.json` — a happy-path event that yields
  `terminal.type == "action"`, `policy_result == "allowed"`,
  `autonomy_class == "safe_autonomous"`. Mirror `FIXTURE-001-happy-path.json`
  structure (copy it, keep `situation_id`/`event_id` distinct, e.g.
  `EVT-7000`/`SIT-7000`).
- `FIXTURE-007-m3-judge-surface-escalation.json` — an event that yields
  `terminal.type == "escalation"`, `autonomy_class == "escalate"` (coverage
  gap or uncertainty). Mirror `FIXTURE-002-escalation.json`.

**Expected assertions file** (`FIXTURE-007-expected.json`) follows the existing
shape (verified): top-level `{"fixture_id, kind, version, assertions: [...]}`.
Add assertions that the M3 proof block (defined in T720) derives correctly:
- `provenance_links` non-empty and contains `event_id`, `coverage_plan_id`,
  `execution_trace_id`, `situation_id`.
- `validation_verdict.state` is `"automated"` for the action fixture and
  `"escalated"` for the escalation fixture.
- `uncertainty_summary` exposes `causality_status`, `confidence`, and the
  `uncertainties` list.
- `human_control_state` is `"automated"` (action) / `"escalated"` (escalation)
  and the escalation case carries `required_human_role`.

**Acceptance:** `python scripts/run_fixture.py` exits 0 for both 007 inputs;
the new expected-assertions file loads and is satisfied by the pipeline.

---

## T720 — `GET /api/v1/situations/{situation_id}` + M3 proof block

**Files:**
- Edit `src/forgemind/api.py` (add route + a pure helper `build_m3_proof`).
- New module `src/forgemind/m3_proof.py` (pure derivation, no I/O, unit-testable).

**Step 1 — `src/forgemind/m3_proof.py`:** implement
`build_m3_proof(pipeline_result: dict) -> dict` returning exactly:

```python
{
  "provenance_links": {
    "event_id": <artifacts.coverage_plan.provenance.event_id>,
    "coverage_plan_id": <artifacts.coverage_plan.coverage_plan_id>,
    "execution_trace_id": <trace_id from pipeline_result>,
    "situation_id": <situation_id from pipeline_result>,
    "artifact_chain": [  # ordered lineage with upstream refs
      {"artifact": "coverage_plan", "id": <coverage_plan_id>,
       "upstream": ["event_id"]},
      {"artifact": "evidence_shards", "id": <count or ids>,
       "upstream": ["coverage_plan_id"]},
      {"artifact": "domain_findings", "id": <ids>,
       "upstream": ["evidence_shard_ids"]},
      {"artifact": "validated_situation", "id": <id>,
       "upstream": ["finding_ids", "coverage_plan_id"]},
      {"artifact": "decision_record", "id": <id>,
       "upstream": ["validated_situation_id"]},
      {"artifact": "action_validation", "id": <validation_id>,
       "upstream": ["action_id"]},
      {"artifact": "terminal", "id": <action_id or escalation_id>,
       "upstream": ["validation_id"]},
    ],
  },
  "validation_verdict": {
    "state": "automated" | "human_review" | "escalated",
    "policy_result": <action_validation.policy_result or None>,
    "reason": <action_validation.reason or escalation.reason>,
    "validation_id": <action_validation.validation_id or None>,
  },
  "uncertainty_summary": {
    "causality_status": <validated_situation.causality_status>,
    "confidence": <validated_situation.confidence>,
    "missing_domains": <validated_situation.coverage.missing_domains>,
    "coverage_percentage": <validated_situation.coverage.coverage_percentage>,
    "uncertainties": <union of validated_situation.uncertainties
                      and decision_record.uncertainties>,
  },
  "human_control_state": {
    "state": "automated" | "human_review_required" | "escalated",
    "autonomy_class": <decision_record.autonomy_class>,
    "required_human_role": <escalation.required_human_role or None>,
    "risk_level": <decision_record.risk_level>,
  },
}
```

Derivation rules (exact):
- `validation_verdict.state`:
  - if `terminal.type == "action"` and `policy_result == "allowed"` → `"automated"`.
  - elif `policy_result == "requires_human"` → `"human_review"`.
  - else (`escalated` / `rejected`) → `"escalated"`.
- `human_control_state.state`: same mapping as above using `autonomy_class`
  for the label when present; escalation ⇒ `"escalated"`.
- All values pulled defensively (`.get`) so a missing key yields `None`, never
  a crash.

**Step 2 — `api.py` route:** add
```python
@app.get("/api/v1/situations/{situation_id}")
async def get_situation(situation_id: str):
    # M3-A: derive proof block from a re-run of the pipeline is NOT required;
    # the situation endpoint accepts a posted result OR replays FIXTURE by id.
```
Because the runtime is stateless (no store), the endpoint should accept the
same `EventInput` body and return `{...run_pipeline output..., m3_proof:
build_m3_proof(result)}`. Keep the existing `POST /api/v1/events` unchanged
except to also attach `m3_proof` to its response (call `build_m3_proof` there
too — small, additive).

**Acceptance:**
- `POST /api/v1/events` response now contains `m3_proof` with the four blocks.
- `GET /api/v1/situations/{id}` returns the same proof block for a valid event.
- No tier module (`acquisition/supervisor/workers/domain_managers/validator/
  reducer/action_gate`) is modified except `api.py` importing `build_m3_proof`.
- Full suite stays green: `pytest tests/` → 127 passed (plus new T722 tests).

---

## T721 — Read-only HTML situation viewer

**File:** edit `src/forgemind/api.py` (add one route returning `HTMLResponse`).
No new dependency — render a static HTML string (inline CSS, no JS framework).
If you want a template file, add `src/forgemind/templates/situation.html` and
read it at startup; otherwise inline the string.

**Route:** `GET /` (and `GET /view/{situation_id}` aliased to same handler).
Handler: accept an optional `event` query param OR just render the M3 proof for
`FIXTURE-001` by default (call `run_pipeline` on the loaded FIXTURE-001 input).
Return HTML that visually shows the four M3 properties:
1. **Lineage graph** — ordered `artifact_chain` as a horizontal flow
   (Event → CoveragePlan → EvidenceShards → DomainFindings → ValidatedSituation
   → DecisionRecord → ActionValidation → Terminal), each node showing its id and
   upstream refs.
2. **Validation badge** — colored pill for `validation_verdict.state`
   (green=automated, amber=human_review, red=escalated) + `reason`.
3. **Uncertainty callouts** — `causality_status`, `confidence`,
   `missing_domains`, and each item in `uncertainties` as a list.
4. **Human-control banner** — `human_control_state.state` + `required_human_role`
   (if present) + `risk_level`.

**Acceptance:**
- `GET /` returns 200 HTML containing the strings "provenance", "validation",
  "uncertainty", "human control" and the FIXTURE-001 `situation_id`.
- Rendering reads ONLY `build_m3_proof` output — no tier re-implementation.
- No external assets (CDN) required; works offline.

---

## T722 — M3 surface contract tests

**File to create:** `tests/contract/test_m3_surface.py`

Mirror the integration test pattern in `tests/integration/test_fixture_run.py`
(loads `fixtures/inputs/*.json`, runs `forgemind.api.run_pipeline`).

Tests (use FIXTURE-001 for action path, FIXTURE-002 for escalation path):
1. `test_m3_proof_present_on_events_response` — `run_pipeline` result contains
   `m3_proof` with the four top-level keys.
2. `test_provenance_links_have_trace_ids` — `provenance_links` contains
   `event_id`, `coverage_plan_id`, `execution_trace_id`, `situation_id`, and
   `artifact_chain` has 7 entries in lineage order.
3. `test_validation_verdict_action` — FIXTURE-001 → `validation_verdict.state
   == "automated"`, `policy_result == "allowed"`.
4. `test_validation_verdict_escalation` — FIXTURE-002 → `validation_verdict.
   state == "escalated"`, `human_control_state.required_human_role` is set.
5. `test_uncertainty_summary_shape` — `uncertainty_summary` has
   `causality_status`, numeric `confidence`, `missing_domains` list,
   `uncertainties` list.
6. `test_human_control_state_derivation` — action fixture ⇒ `"automated"`;
   escalation fixture ⇒ `"escalated"` with non-null `required_human_role`.

**Acceptance:** `pytest tests/contract/test_m3_surface.py` → 6 passed; full
suite → 127 + 6 = 133 passed.

---

## Execution order & gates for Cline

1. T711 (fixtures) — no code, unblocks T722.
2. T720 (`m3_proof.py` + `api.py` route + attach to events response).
3. T721 (HTML route) — depends on T720's `build_m3_proof`.
4. T722 (tests) — depends on T711 + T720.

Run `pytest tests/` after EACH step. Do NOT touch tiers, contracts, or
`pyproject.toml`. The 127 existing tests must remain green throughout; only
the count grows by the new M3 tests.

## Definition of Done (M3-A)
- `/api/v1/events` returns `m3_proof` with the four blocks for every fixture.
- `/api/v1/situations/{id}` and `/` viewer render provenance, validation,
  uncertainty, human control.
- `FIXTURE-007` (action + escalation) added with expected assertions.
- `pytest tests/` green (133 total). No tier/contract/dependency changes.
