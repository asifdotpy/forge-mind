# ForgeMind v3.0 — Demo Video Script (~4 min, unedited live demo)

**Frame:** Screen-capture of terminal + browser. Show real runs, not slides.
Speak to the three hackathon judging pillars: Utility (40%), Architecture (30%),
Demo/Production Readiness (30%).

**Pre-demo setup:**
- Terminal with `PYTHONPATH=src` and `.venv` activated
- Browser open to Cloud Run dashboard
- `SUBMISSION/ARCHITECTURE.md` open in another tab
- Real PR ready on GitHub (PR #210, #204, #192, #195)

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
- **Architecture explanation:** "Our logical architecture is hierarchical: each Domain Manager owns two Specialist Workers. The current implementation uses a flat pipeline for simplicity — the pipeline dispatches workers first, then managers aggregate. The ownership hierarchy is preserved in the code: each Manager owns exactly 2 Workers. This is a known design debt we plan to address post-hackathon."

---

## 1:30–2:30 — Real PR analysis (utility pillar)

- **Trigger webhook for PR #210** (CI + Docs + Scripts):
  ```bash
  curl -X POST $URL/api/v1/adk/webhook -d '{"action":"opened","number":210,...}'
  ```
- Show the comment posted on GitHub: confidence 0.23, risk high, escalate
- **Trigger webhook for PR #204** (Dependabot CI only):
  ```bash
  curl -X POST $URL/api/v1/adk/webhook -d '{"action":"opened","number":204,...}'
  ```
- Show different comment: confidence 0.18, risk high, escalate
- **Compare both PRs**: "Different files → different confidence scores. Evidence-derived, not heuristic."

---

## 2:30–3:30 — Full dashboard view (the differentiator)

- Open `https://forgemind-n3nupsii5a-uc.a.run.app/view/SIT-GITHUB-210`
- Show the full M3 dashboard: evidence chain, uncertainty, analytics, human control
- Point out: "This is not a hardcoded mockup. This is real data from a real GitHub PR."
- Show PR #204 dashboard: different evidence states, different confidence
- "Every PR gets its own unique dashboard URL linked from the comment."

---

## 3:30–4:00 — Production readiness + close

- Show Cloud Run dashboard (proof it runs on Google Cloud).
- `uv run pytest tests/` → **298 passed, 1 skipped**.
- "Reproducible: clone, `uv sync`, `uv run pytest`. Deployed on Cloud Run."
- "ForgeMind — autonomous, evidence-driven, human-aware."

---

## Tips

- Keep it one unedited take. Show the terminal output, not a recap.
- Have creds ready off-screen; fall back to deterministic if the network lags.
- Show the real PR comment posted on GitHub as proof of action.

---

**Key numbers to mention:**
- 298 tests passed
- 5-tier DAG
- 6 specialist workers
- 3 runtime modes (deterministic, adk, adk+runner)
- File-derived domains + evidence-derived confidence
- Real PRs: #210 (0.23), #204 (0.18), #192 (0.22), #195 (0.40)
