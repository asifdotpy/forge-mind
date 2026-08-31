# ForgeMind v3.0 — Demo Video Script

**Frame:** Screen-capture of terminal + browser. Show real runs, not slides.
**Commands:** `SUBMISSION/DEMO_COMMANDS.md` — copy-paste from there

---

## 0:00–0:30 — Introduction & problem

**[You on camera or voiceover]**

> "Hey, I'm Asif Iqbal. I built ForgeMind.
>
> Here's the problem. AI writes code fast now — but review, validation, coordination? Still takes days. A PR sits waiting. A flaky build goes unnoticed. An incident happens and nobody connects it to the deploy from this morning.
>
> ForgeMind fixes that. It's an autonomous engineering control plane that correlates signals across the lifecycle — and knows when to act versus when to ask a human."

---

## 0:30–1:30 — Architecture

**[Show SUBMISSION/ARCHITECTURE.md]**

> "Five tiers. Strict boundaries.
>
> Event comes in here. Supervisor creates a coverage plan. Then six specialist workers produce evidence — code analysis, build logs, alerts, security scans. Three domain managers aggregate those into findings. The validator reconciles across domains. The reducer applies autonomy policy. And this gate? No-bypass. Every action goes through it.
>
> Workers never decide. Only the Reducer decides.
>
> We also have ADK Runner mode — Google ADK agents call tools that execute the tiers. The agent actually takes decisions.
>
> Now, our logical architecture is hierarchical — each Manager owns two Workers. Right now the implementation uses a flat pipeline for simplicity. Workers run first, then managers aggregate. The ownership is preserved in code. It's a design debt — we'll fix it post-hackathon."

---

## 1:30–2:30 — Real PR analysis

**[Show PR #210 on GitHub]**

> "Let me show this working. This is PR #210 — touches CI workflows, docs, and a Python script.
>
> I'll trigger the webhook manually. In production, GitHub webhooks do this automatically."

**[Run PR #210 command from DEMO_COMMANDS.md]**

> "Sent. Let me refresh the PR."

**[Show GitHub PR #210 — comment posted]**

> "There's the comment. Confidence: 0.23. Risk: high. Autonomy: escalate. And this link — `/view/SIT-GITHUB-210` — every PR gets its own dashboard.
>
> Now PR #204. Just a dependabot CI bump. Two YAML files."

**[Run PR #204 command from DEMO_COMMANDS.md]**

> "Confidence: 0.18. Different files, different scores. Evidence-derived — not heuristic."

---

## 2:30–3:30 — Full dashboard view

**[Open /view/SIT-GITHUB-210 in browser]**

> "Let me click that link."

**[Show full dashboard]**

> "This isn't a hardcoded mockup. This is real data from that PR. Evidence shards. Domain findings. Validated situation. Decision record. Action validation. Full provenance chain.
>
> What happened? Why? How confident? Did ForgeMind act? Who controls the next step? It's all here."

**[Open /view/SIT-GITHUB-204]**

> "PR #204's dashboard — different evidence, different confidence. Every PR gets its own."

---

## 3:30–4:00 — Production readiness + close

**[Show Cloud Run console]**

> "Running on Google Cloud. And reproducible."

**[Run test suite from DEMO_COMMANDS.md]**

> "298 tests passed.
>
> Clone, `uv sync`, `uv run pytest`. That's it.
>
> ForgeMind — autonomous, evidence-driven, human-aware."

---

**Key numbers:** 298 tests | 5-tier DAG | 6 workers | PR #210 (0.23) | PR #204 (0.18)
