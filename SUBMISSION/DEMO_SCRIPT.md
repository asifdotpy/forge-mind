# ForgeMind v3.0 — Demo Video Script

**Frame:** Screen-capture of terminal + browser. Show real runs, not slides.
**Commands:** `SUBMISSION/DEMO_COMMANDS.md` — copy-paste from there

---

## 0:00–0:30 — Introduction & problem

> "Hey, I'm Asif Iqbal. I built ForgeMind.
>
> AI writes code fast now — but review, validation, coordination? Still takes days. A PR sits waiting. A flaky build goes unnoticed. An incident happens and nobody connects it to the deploy from this morning.
>
> ForgeMind fixes that. It correlates signals across the lifecycle — and knows when to act versus when to ask a human."

---

## 0:30–1:30 — Architecture

**[Show SUBMISSION/ARCHITECTURE.md]**

> "Five tiers. Workers emit evidence. Managers aggregate. Validator reconciles. Reducer decides. Gate enforces — no bypass.
>
> ADK Runner mode — agents call tools that execute the tiers. The agent actually takes decisions.
>
> Logical architecture is hierarchical — each Manager owns two Workers. Current implementation uses a flat pipeline for simplicity. Known design debt, post-hackathon fix."

---

## 1:30–2:30 — Real PR analysis

**[Show PR #210 on GitHub]**

> "PR #210 — CI, docs, and a Python script. Triggering webhook manually."

**[Run PR #210 command from DEMO_COMMANDS.md]**

> "Sent. Refreshing the PR."

**[Show GitHub PR #210 — comment posted]**

> "There's the comment. Confidence: 0.23. Risk: high. Escalate. And this link — every PR gets its own dashboard.
>
> PR #204 — dependabot CI bump. Two YAML files."

**[Run PR #204 command from DEMO_COMMANDS.md]**

> "Confidence: 0.18. Different files, different scores. Evidence-derived."

---

## 2:30–3:30 — Full dashboard view

**[Open /view/SIT-GITHUB-210 in browser]**

> "Clicking the link."

**[Show full dashboard]**

> "Not a hardcoded mockup. Real data from that PR. Evidence chain, provenance, uncertainty, human control. All generated from actual artifacts."

**[Open /view/SIT-GITHUB-204]**

> "PR #204 — different evidence, different confidence."

---

## 3:30–4:00 — Production readiness + close

**[Show Cloud Run console]**

> "Running on Google Cloud. And reproducible."

**[Run test suite from DEMO_COMMANDS.md]**

> "298 tests passed. Clone, `uv sync`, `uv run pytest`. That's it.
>
> ForgeMind — autonomous, evidence-driven, human-aware."

---

**Key numbers:** 298 tests | 5-tier DAG | 6 workers | PR #210 (0.23) | PR #204 (0.18)
