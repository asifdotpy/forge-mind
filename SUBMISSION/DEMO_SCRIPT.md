# ForgeMind v3.0 — Demo Video Script (~4 min, unedited live demo)

**Frame:** screen-capture of terminal + browser. Show real runs, not slides.
Speak to the three hackathon judging pillars: Utility (40%), Architecture (30%),
Demo/Production Readiness (30%).

## 0:00–0:30 — Problem & value proposition (live, no slides)
- "Engineering teams drown in disconnected signals: a PR, a flaky build, a
  production alert — nobody connects them." Show `docs/PROJECT.md` core problem.
- "ForgeMind is an autonomous control plane that correlates them across the
  lifecycle and knows when to act — and when to ask a human."

## 0:30–1:30 — Architecture (diagram + real code)
- Open `SUBMISSION/ARCHITECTURE.md` (Mermaid) — the five-tier DAG.
- Open `src/forgemind/` — name each tier file. Emphasize **strict boundaries**:
  workers emit evidence, never decide; only the Reducer decides; the gate
  enforces no-bypass. This is the "Architectural Discipline" pillar.
- Mention the **Fortified Enterprise Fleet** fit: ADK 2 + GenAI SDK + Cloud Run,
  Model Armor-style bounded Gemini, OpenTelemetry-style provenance.

## 1:30–2:30 — Autonomous action (utility pillar)
- Run `PYTHONPATH=src uv run python scripts/run_fixture.py` → show all 7
  fixtures, **0 errors**, full lineage.
- `curl -X POST .../api/v1/events` with `FIXTURE-001` (happy path) →
  terminal action, `policy_result=allowed`, `autonomy_class=safe_autonomous`.
  "Low-risk action, automated — that's the friction removed."

## 2:30–3:30 — Human control + AI core (the differentiator)
- Show `GET /` viewer: provenance chain, validation badge, uncertainty
  callouts, human-control banner. This is the **judge-visible M3 surface**.
- Enable the AI core live:
  ```bash
  export FORGEMIND_RUNTIME=adk VERTEX_PROJECT=... GOOGLE_API_KEY=...
  ```
  Re-run `FIXTURE-001` → point at the Gemini-backed `observations` in the code
  worker's EvidenceShard. "Real Gemini 3.5 via Vertex AI, bounded to one
  worker node — it fills evidence text, never decisions."
- Force a `requires_human` case → show `status: paused` + approval token;
  `POST /api/v1/approvals/{token}` approve → escalation published; reject →
  no action. "High-blast-radius actions stop for a human. Autonomy proportional
  to risk."

## 3:30–4:00 — Production readiness + close
- Show Cloud Run dashboard / Vertex AI logs (proof it runs on Google Cloud).
- `uv run pytest tests/` → **236 passed, 1 skipped**.
- "Reproducible: clone, `uv sync`, `uv run pytest`. Deployed on Cloud Run.
  ForgeMind — autonomous, evidence-driven, human-aware."

## Tips
- Keep it one unedited take. Show the terminal output, not a recap.
- Have `FORGEMIND_RUNTIME=adk` creds ready off-screen; fall back to
  deterministic if the network lags (the demo still proves the surface).
