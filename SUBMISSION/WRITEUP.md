# ForgeMind v3.0 — Hackathon Submission Writeup

**Hackathon:** All Things Agentic Hackathon
**Track:** The Fortified Enterprise Fleet
**Repo:** https://github.com/asifdotpy/forge-mind (public)

## What we built
ForgeMind is an autonomous **engineering control plane** that takes a real
engineering event (a PR, a build failure, a production alert) and runs it
through a strict five-tier hierarchical DAG: Supervisor → Domain Managers →
Specialist Workers → Cross-Lifecycle Validator → Decision Reducer. The system
produces durable, provenance-tracked evidence, reconciles it across domains,
and only then decides — automating low-risk actions and escalating
high-blast-radius ones to a human.

## Features & functionality
- **Five-tier hierarchical DAG** with enforced authority boundaries (workers
  never decide; the Reducer is the sole decision authority; the ActionValidation
  gate is a no-bypass publish point).
- **Deterministic, schema-validated artifact lineage** (`Event → … → Action |
  Escalation`) with upstream provenance on every artifact.
- **Real Gemini 3.5 via Vertex AI** (Google GenAI SDK) bounded to a single
  worker node — it generates evidence narrative, never decisions, and fails
  closed to deterministic output on any error.
- **Google ADK 2 workflow** (`adk_runtime.py`) wrapping the DAG with explicit,
  pause/resume-capable stages and a **human-approval gate**.
- **Judge-visible M3 surface** (`GET /api/v1/situations/{id}`, `GET /` HTML
  viewer) proving the four properties judges care about: **provenance,
  validation, uncertainty, human control**.
- **Deployed on Google Cloud Run** (`forgemind-v3-prod`, us-central1).

## Technologies used
- **Gemini 3.5 Flash via Vertex AI** (`google-genai`) — bounded LLM reasoning.
- **Google ADK 2** — workflow orchestration, pause/resume.
- **Google Cloud Run** — deployment / inference surface.
- Python ≥ 3.11, `uv`, FastAPI, JSON Schema (9 canonical contracts), pytest,
  `ggshield` secret scanning.
- Notion Knowledge Brain (dev-time ChromaDB, ADR-009) for planning grounding.

## Other data sources
- Canonical specifications and ADRs in `specs/001-hierarchical-runtime-dag/`
  and `docs/decisions/`; fixtures under `fixtures/`.

## Findings & learnings
- **Bounded LLM scope beats an LLM-everywhere design.** Confining Gemini to one
  worker node kept the deterministic 231-test suite green and preserved the
  architectural invariants judges reward (Architectural Discipline pillar).
- **Provenance is a feature, not overhead.** Carrying `execution_trace_id` and
  upstream refs through every artifact made the "human control" story trivially
  demonstrable.
- **Fail-closed AI integration** (deterministic fallback on any model error)
  means the system is safe to demo even if the model is unavailable.

## How it meets the mandatory requirements
1. Gemini 3.5 via Vertex AI ✅ · 2. Google ADK 2 **and** GenAI SDK ✅ ·
   3. Cloud Run ✅.

## Known gaps (disclosed)
- Runtime Memory Bank is deferred (ADR-009 keeps ChromaDB dev-only); durable
  cross-session memory is a post-M3 item.
- Model Armor is realized via in-code deterministic guardrails + bounded Gemini
  scope, not the managed service (post-M3 hardening).
