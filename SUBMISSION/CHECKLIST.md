# ForgeMind v3.0 — Hackathon Submission Checklist

**Hackathon:** All Things Agentic Hackathon · **Track:** The Fortified
Enterprise Fleet · **Deadline:** 2026-08-31 8:00pm EDT

## Mandatory requirements (every project)
- [x] Gemini 3.5+ via Gemini API or Vertex AI → `google-genai` (Vertex AI),
      `src/forgemind/llm/adapter.py`
- [x] ≥1 Google Agent Framework → **ADK 2** (`adk_runtime.py`) **and** **GenAI
      SDK** (`google-genai`)
- [x] ≥1 GCP infra service → **Cloud Run** (`forgemind-v3-prod`, us-central1)

## What to Submit (per Devpost rules)
- [x] **Category** — The Fortified Enterprise Fleet
- [x] **Hosted project URL** — Cloud Run service (deploy + scale-to-zero; show
      in demo video). Local `uv run uvicorn` also works for judges.
- [x] **Text description** — `SUBMISSION/WRITEUP.md` (features, tech, data
      sources, findings)
- [x] **Public code repo** — https://github.com/asifdotpy/forge-mind (public);
      share with testing@devpost.com + cloudhackathons@google.com if needed
- [x] **Spin-up instructions** — `SUBMISSION/SPINUP.md` (reproducible local +
      GCP deploy)
- [x] **Architecture diagram** — `SUBMISSION/ARCHITECTURE.md` (Mermaid + fleet
      capability map + requirement coverage)
- [x] **~4-min demo video** — script in `SUBMISSION/DEMO_SCRIPT.md`; show live
      Cloud Run + Vertex AI logs, unedited run, `pytest` green

## Pre-submission verification (run locally)
- [x] `uv run pytest tests/` → 140 passed
- [x] `PYTHONPATH=src uv run python scripts/run_fixture.py` → 0 errors
- [x] `GET /` viewer shows provenance / validation / uncertainty / human
      control
- [x] `FORGEMIND_RUNTIME=adk` + Vertex creds → Gemini-backed observations;
      `requires_human` pauses; approval endpoint works
- [x] No secrets committed (`ggshield` + `tests/test_secret_handling.py`)

## Optional bonus (not required)
- [ ] Publish a blog/post (#AllThingsAgenticHackathon)
- [ ] Integrate Gemma / Veo / Lyria
- [ ] Managed Model Armor + durable Memory Bank (post-M3 hardening)

## Status at commit time
- M1 local slice ✅ · M2 Cloud Run ✅ · M3 judge surface + AI core ✅
- ADR-001/008 fulfilled; 140 tests green; 9 ADRs; 6 fixtures.
