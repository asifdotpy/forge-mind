# ForgeMind v3.0 — Demo Video Script (Exact Dialogue)

**Frame:** Screen-capture of terminal + browser. Show real runs, not slides.
Speak to the three hackathon judging pillars: Utility (40%), Architecture (30%),
Demo/Production Readiness (30%).

**Commands file:** `SUBMISSION/DEMO_COMMANDS.md` — copy-paste from there

---

## 0:00–0:30 — Problem & value proposition

**Say:**
> "Engineering teams drown in disconnected signals: a PR, a flaky build, a production alert — nobody connects them.
>
> ForgeMind is an autonomous control plane that correlates them across the lifecycle and knows when to act — and when to ask a human.
>
> Built on Google Cloud Run, uses Gemini 3.5, and Google ADK 2.0 for agent composition."

---

## 0:30–1:30 — Architecture

**Say:**
> "Here's the architecture. Five tiers. Event comes in, gets acquired, coverage plan generated. Then specialist workers produce evidence shards. Domain managers aggregate those into findings. The validator reconciles across domains. The reducer applies autonomy policy. And the action gate enforces authorization boundaries — no bypass.
>
> Strict boundaries: workers emit evidence, they never decide. Only the Reducer decides. And the gate enforces no-bypass.
>
> We also have ADK Runner mode — ADK agents now call tools that execute the deterministic tiers. The agent actually takes decisions.
>
> Now, our logical architecture is hierarchical: each Domain Manager owns two Specialist Workers. The current implementation uses a flat pipeline for simplicity — the pipeline dispatches workers first, then managers aggregate. The ownership hierarchy is preserved in the code: each Manager owns exactly 2 Workers. This is a known design debt we plan to address post-hackathon."

**Show:**
- `SUBMISSION/ARCHITECTURE.md` — the five-tier DAG
- `src/forgemind/` — name each tier file

---

## 1:30–2:30 — Real PR analysis

**Say:**
> "Let me show this working on a real GitHub PR. This is PR #210 — it touches CI workflows, docs, and a Python script.
>
> I'm going to trigger the webhook manually. In production, this would be automatic via GitHub webhook configuration."

**Run:** (copy from DEMO_COMMANDS.md — Webhook Test PR #210)

**Say:**
> "The webhook returned successfully. Now let me refresh the PR on GitHub."

**Show:**
- GitHub PR #210 — comment is posted

**Say:**
> "Here's the comment. Confidence: 0.23. Risk: high. Autonomy: escalate. And here's the key — this unique dashboard link: `/view/SIT-GITHUB-210`. Every PR gets its own.
>
> Now let me show a different PR. This is PR #204 — just a dependabot CI bump. Two YAML files, nothing else."

**Run:** (copy from DEMO_COMMANDS.md — Webhook Test PR #204)

**Say:**
> "PR #204: confidence 0.18. PR #210: confidence 0.23. Different files → different confidence scores. Evidence-derived, not heuristic."

**Show:**
- GitHub PR #204 — comment is posted

---

## 2:30–3:30 — Full dashboard view

**Say:**
> "Now let me click that dashboard link. This is `/view/SIT-GITHUB-210`."

**Open in browser:**
```
https://forgemind-n3nupsii5a-uc.a.run.app/view/SIT-GITHUB-210
```

**Say:**
> "This is not a hardcoded mockup. This is real data from a real GitHub PR. Evidence shards, domain findings, validated situation, decision record, action validation — the full provenance chain.
>
> What happened? Safety gate? Next steps? It's all here. And it's generated from the actual artifacts, not hardcoded values.
>
> Let me show PR #204's dashboard — different evidence states, different confidence."

**Open:**
```
https://forgemind-n3nupsii5a-uc.a.run.app/view/SIT-GITHUB-204
```

**Say:**
> "Every PR gets its own unique dashboard URL linked from the comment."

---

## 3:30–4:00 — Production readiness + close

**Say:**
> "This is running on Google Cloud. Let me show you the Cloud Run dashboard."

**Show:**
- Cloud Run console — service running, metrics

**Say:**
> "And reproducibility. Let me run the test suite."

**Run:** (copy from DEMO_COMMANDS.md — Test Suite)

**Say:**
> "298 tests passed, 1 skipped.
>
> Reproducible: clone, `uv sync`, `uv run pytest`. Deployed on Cloud Run.
>
> ForgeMind — autonomous, evidence-driven, human-aware."

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
