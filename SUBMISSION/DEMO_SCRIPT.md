# ForgeMind v3.0 — Demo Video Script (~4 min, unedited live demo)

**Frame:** Screen-capture of terminal + browser. Show real runs, not slides.
Speak to the three hackathon judging pillars: Utility (40%), Architecture (30%),
Demo/Production Readiness (30%).

**Pre-demo setup:**
- Terminal with `PYTHONPATH=src` and `.venv` activated
- Browser open to Cloud Run dashboard
- `SUBMISSION/ARCHITECTURE.md` open in another tab
- Real PR ready on GitHub (for webhook test)

---

## 0:00–0:30 — Problem & value proposition (live, no slides)

- "Engineering teams drown in disconnected signals: a PR, a flaky build, a production alert — nobody connects them."
- "ForgeMind is an autonomous control plane that correlates them across the lifecycle and knows when to act — and when to ask a human."
- "Built on Google Cloud Run, uses Gemini 3.5, and Google ADK 2.0 for agent composition."

---

## 0:30–1:30 — Architecture (diagram + real code)

- Open `SUBMISSION/ARCHITECTURE.md` — show the five-tier DAG.
- Open `src/forgemind/` — name each tier file. Emphasize **strict boundaries**:
  - Workers emit evidence, never decide
  - Only the Reducer decides
  - The gate enforces no-bypass
- Show the new `adk+runner` mode: "ADK agents now call tools that execute the deterministic tiers — the agent actually takes decisions."

---

## 1:30–2:30 — Autonomous action (utility pillar)

- Run `PYTHONPATH=src python scripts/run_fixture.py` → show all 7 fixtures, **0 errors**, full lineage.
- Show different PRs producing different outcomes:
  - CI files → domains `['code', 'delivery']` → `safe_autonomous`
  - Docs → domains `['code']` → `human_review`
  - Auth files → domains `['code', 'production']` → `human_review`
- "Evidence-derived confidence — different PRs score differently."

---

## 2:30–3:30 — Human control + ADK Runner (the differentiator)

- Show `GET /` viewer: provenance chain, validation badge, uncertainty callouts, human-control banner.
- Enable ADK Runner live:
  ```bash
  export FORGEMIND_RUNTIME=adk+runner
  ```
- Re-run a PR event → point at the ADK agents calling tools. "Real ADK 2.0 tool calling — the agent executes the five-tier DAG."
- Force a `requires_human` case → show `status: paused` + approval token.
- "High-blast-radius actions stop for a human. Autonomy proportional to risk."

---

## 3:30–4:00 — Production readiness + close

- Show Cloud Run dashboard (proof it runs on Google Cloud).
- `uv run pytest tests/` → **288 passed, 1 skipped**.
- "Reproducible: clone, `uv sync`, `uv run pytest`. Deployed on Cloud Run. ForgeMind — autonomous, evidence-driven, human-aware."

---

## Tips

- Keep it one unedited take. Show the terminal output, not a recap.
- Have `FORGEMIND_RUNTIME=adk+runner` creds ready off-screen; fall back to deterministic if the network lags.
- Show the real PR comment posted on GitHub as proof of action.

---

**Key numbers to mention:**
- 288 tests passed
- 5-tier DAG
- 6 specialist workers
- 3 runtime modes (deterministic, adk, adk+runner)
- File-derived domains + evidence-derived confidence
