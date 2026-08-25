# ADR-010: M3 AI Core Scope — Real Gemini 3.5 via Vertex AI inside bounded ADK 2 nodes

## Status
Accepted

## Date
2026-08-25

## Problem / Context
M3 (Milestone 3 — the judge-visible surface) requires proving provenance,
validation, uncertainty, and human control. The *presentation* of these four
properties (M3-A) is fully achievable over the existing deterministic five-tier
DAG with no tier changes. However, the project's stated architecture
(ADR-001 Google Cloud mapping; ADR-008 ADK 2 runtime) calls for real LLM
reasoning — "Gemini 3.5 via Vertex AI" — inside bounded agent nodes, and both
ADRs are currently recorded as *unfulfilled*. For a hackathon entry judged on an
"intelligent autonomous control plane," a deterministic-only M3 understates the
approved architecture.

T710 (specs/001-hierarchical-runtime-dag/plan.md, M3-0 scope gate) required
this decision before any M3-B code:
- (a) deterministic representative slice, **or**
- (b) real Gemini 3.5 via Vertex AI inside bounded ADK 2 nodes.

## Decision
Adopt **option (b)**: M3 includes the real AI core. M3-B is now UNBLOCKED.

- The five-tier DAG and its authority boundaries (Supervisor / Manager /
  Worker / Validator / Reducer, plus the ActionValidation gate) are preserved
  exactly as implemented. No tier gains authority it does not already have.
- A bounded LLM reasoning node, powered by **Gemini 3.5 via Vertex AI**, is
  introduced at ONE designated Tier 3 worker (code-intelligence) to produce the
  natural-language narrative of its `EvidenceShard`. The worker's *schema
  contract* (EvidenceShard shape, provenance, bounded-domain guard) is
  unchanged; only the narrative content source changes from deterministic stub
  to model-generated text.
- Orchestration is migrated onto **Google ADK 2** as the workflow runtime per
  ADR-008: deterministic stage transitions, state graph, pause/resume, and a
  human-approval gate node at the action gate. ADK manages *orchestration*;
  it does not make decisions — the Reducer remains the sole decision authority.
- A human-approval gate node (ADK pause/resume) is inserted before any terminal
  `action` whose `risk_level` exceeds the supervised threshold
  (`require_human_above_risk_level`), making human control explicit and
  demonstrable in the M3 surface.

## Consequences

### Positive
- Fulfills ADR-001 / ADR-008 (previously "unfulfilled"), aligning the shipped
  system with the approved Google Cloud stack narrative.
- Demonstrates real LLM reasoning where it adds value (evidence narrative) while
  keeping high-stakes decision/validation logic deterministic and auditable.
- Judges see both: a genuine Gemini-powered analysis node AND the structural
  guardrails (no-bypass gate, human escalation) intact.

### Trade-offs / Risks (must be managed)
- **New runtime dependency**: `google-genai` (or `google-cloud-aiplatform`)
  enters `[project].dependencies`. This weakens the "zero external runtime
  deps beyond FastAPI" property and means the image can no longer run fully
  offline. Mitigation: tie model calls behind a single `llm/` adapter module
  so the rest of the runtime stays model-agnostic; provide a deterministic
  fallback path when `VERTEX_PROJECT`/`GOOGLE_API_KEY` are absent so the 127
  existing tests (and `run_fixture.py`) still pass with NO model configured.
- **ADR-009 boundary test must be EXTENDED, not weakened**: the runtime import
  surface hard-coded in `tests/contract/test_runtime_boundary.py` gains the new
  `llm` module; the ChromaDB blocker test MUST continue to pass — ChromaDB
  remains dev-only and absent from the production image. Gemini must never pull
  ChromaDB into runtime scope.
- **Determinism of 127-test suite**: model output is non-deterministic, so no
  existing contract test may assert specific model text. The Gemini node's
  outputs are validated only for *shape* (EvidenceShard schema) and *provenance*
  (trace IDs), never for content. Preserve the deterministic fixtures as the
  contract-truth source; Gemini is additive, not a fixture replacement.
- **Credential exposure**: Vertex AI credentials at runtime require Secret
  Manager / Workload Identity (ADR-001 Security & Guardrails). No key is
  committed; ggshield pre-commit + secret-handling tests remain authoritative.
- **Cost**: live Gemini calls cost tokens; M3 demo must use a small, cached, or
  capped call budget. Keep the deployed Cloud Run service scaled to zero when
  not demoing (as done for M2).

## Verification
- T730: ADK 2 workflow scaffold wraps the DAG; existing 127 tests still green
  with model adapter in deterministic-fallback mode.
- T731: Gemini node produces schema-valid EvidenceShard narrative for
  code-intelligence worker; provenance preserved; no contract change.
- T732: human-approval gate node fires for above-threshold risk; M3 surface
  shows `human_control_state`.
- T733: ADK integration tests green; M2 re-deployed with ADK-enabled image;
  ADR-009 boundary test still passes (ChromaDB absent at runtime).
- `tests/contract/test_runtime_boundary.py` updated to include the new `llm`
  module in the import surface and to re-assert ChromaDB stays dev-only.

## Relationship to other ADRs
- Supersedes the "unfulfilled" status of ADR-001 §Reasoning Model and ADR-008
  (both now in-execution under M3-B).
- Does NOT modify ADR-009: ChromaDB remains CONTEXT, not AUTHORITY, dev-only.
- Does NOT modify tier authority boundaries (ADR-003/004/005/006/007).
