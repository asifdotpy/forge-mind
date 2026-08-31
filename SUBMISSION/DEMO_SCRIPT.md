# ForgeMind v3.0 — Demo Video Script (Short)

**Frame:** Screen-capture of terminal + browser. Show real runs, not slides.
**Commands:** `SUBMISSION/DEMO_COMMANDS.md` — copy-paste from there

---

## 0:00–0:30 — Problem & value proposition

> "PRs, builds, alerts — nobody connects them. ForgeMind does. It knows when to act and when to ask a human. Built on Cloud Run, Gemini 3.5, ADK 2.0."

---

## 0:30–1:30 — Architecture

> "Five tiers. Workers emit evidence. Only the Reducer decides. Gate enforces no-bypass. ADK agents call tools that execute the tiers.
>
> Logical architecture is hierarchical — each Manager owns 2 Workers. Current implementation uses a flat pipeline for simplicity. Known design debt, post-hackathon fix."

**Show:** `SUBMISSION/ARCHITECTURE.md` + `src/forgemind/`

---

## 1:30–2:30 — Real PR analysis

> "PR #210 — CI, docs, and a Python script. Triggering webhook manually."

**Run:** (DEMO_COMMANDS.md — PR #210)

> "Comment posted. Confidence 0.23, risk high, escalate. Unique dashboard link included.
>
> PR #204 — dependabot CI bump. Two YAML files."

**Run:** (DEMO_COMMANDS.md — PR #204)

> "Confidence 0.18. Different files → different scores. Evidence-derived."

**Show:** Both comments on GitHub

---

## 2:30–3:30 — Full dashboard view

> "Clicking the link — `/view/SIT-GITHUB-210`."

**Open:** `https://forgemind-n3nupsii5a-uc.a.run.app/view/SIT-GITHUB-210`

> "Not a hardcoded mockup. Real data from a real PR. Evidence chain, provenance, uncertainty, human control."

**Show:** `/view/SIT-GITHUB-204` — different evidence, different confidence

---

## 3:30–4:00 — Production readiness + close

> "Running on Google Cloud."

**Show:** Cloud Run console

> "Reproducible."

**Run:** (DEMO_COMMANDS.md — Test Suite)

> "298 tests passed. ForgeMind — autonomous, evidence-driven, human-aware."

---

**Key numbers:** 298 tests | 5-tier DAG | 6 workers | PR #210 (0.23) | PR #204 (0.18)
