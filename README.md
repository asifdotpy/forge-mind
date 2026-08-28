# ForgeMind — Hierarchical Engineering Agent System

> **ForgeMind is an autonomous engineering control plane where specialized agents share context, understand relationships across the software lifecycle, reduce operational friction, and know when to act — and when to ask a human.**

**Status:** 🟢 SPEC-001 Complete — Five-Tier Runtime + M3 Judge Surface Implemented (Phases 1-6, M1/M2/M3 done, 231 passed + 1 skipped, real Gemini 3.5 via Vertex AI + ADK 2)

## What ForgeMind Is

- **A 5-Tier Hierarchical DAG** — strict separation of global supervision, domain management, specialist investigation, evidence validation, and decision reduction.
- **An Evidence-Driven Control Plane** — leaf workers emit structured, verifiable `EvidenceShard`s; cross-domain reconciliation occurs strictly before decisions are made.
- **A Fortified Enterprise Fleet** — built on Google ADK 2, Vertex AI Gemini, and Model Armor guardrails, designed for enterprise safety and human escalation.

### The Five Tiers

```
Event Sources → Acquire Layer (Event Gateway)
    → Tier 1: Engineering Supervisor        (CoveragePlan)
    → Tier 2: Domain Managers ×3            (DomainFinding)
    → Tier 3: Specialist Workers ×6         (EvidenceShard)
    → Tier 4: Cross-Lifecycle Validator     (ValidatedSituation)
    → Tier 5: Decision Reducer & Publisher  (DecisionRecord · ProposedAction · Escalation)
```

Canonical runtime chain: `Acquire → Analyze → Reconcile → Produce → Validate`.

## Repository Layout

| Path | Purpose |
|---|---|
| [`src/forgemind/`](src/forgemind/) | Importable package (tier implementations land phase by phase) |
| [`specs/001-hierarchical-runtime-dag/`](specs/001-hierarchical-runtime-dag/) | Canonical spec: `spec.md`, `plan.md`, `tasks.md`, `data-model.md`, 9 JSON Schema contracts |
| [`fixtures/`](fixtures/) | Phase 0 fixtures (`FIXTURE-001-happy-path.json`, `FIXTURE-002-escalation.json`) + expected assertions |
| [`scripts/`](scripts/) | Fixture runner, Notion knowledge-brain sync, boundary enforcement |
| [`tests/`](tests/) | Contract + integration suites |
| [`docs/`](docs/) | Project vision, architecture, current state, decisions (ADRs), failure log |

## Documentation

- [`docs/PROJECT.md`](docs/PROJECT.md) — North-star vision, core problem, design principles
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — Five-tier DAG, artifact lineage, infrastructure mapping
- [`docs/CURRENT_STATE.md`](docs/CURRENT_STATE.md) — Verified project status (start here)
- [`specs/001-hierarchical-runtime-dag/spec.md`](specs/001-hierarchical-runtime-dag/spec.md) — Canonical executable specification
- [`docs/decisions/`](docs/decisions/) — Architecture Decision Records
- [`SUBMISSION/`](SUBMISSION/) — Hackathon artifacts: `ARCHITECTURE.md` (diagram), `SPINUP.md` (reproducible setup), `DEMO_SCRIPT.md`, `WRITEUP.md`, `CHECKLIST.md`

## Quick Start

```bash
# Requires Python >= 3.11 and uv
uv sync                      # install dependencies (incl. dev group)
uv run pytest tests/         # run the test suite

# Validate a fixture end-to-end (Event schema + expected-artifact coverage)
PYTHONPATH=src python scripts/run_fixture.py fixtures/inputs/FIXTURE-001-happy-path.json
```

## Technology Baseline

- **Reasoning Engine:** Gemini 3.5 via Vertex AI ✅ (ADR-010, `google-genai`)
- **Workflow & Orchestration:** Google ADK 2 ✅ (ADR-008, `adk_runtime.py` workflow graph)
- **Knowledge Brain**: Notion (authoritative) + ChromaDB (dev-time grounding)
- **Contracts:** JSON Schema draft-07 (9 canonical artifacts)
- **Toolchain:** Python ≥ 3.11, pytest, uv, ggshield secret scanning

## License

[MIT](LICENSE)
