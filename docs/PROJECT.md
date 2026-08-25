# ForgeMind — Hierarchical Engineering Agent System

> **Hackathon:** All Things Agentic Hackathon  
> **Track:** The Fortified Enterprise Fleet  
> **Version:** 3.0 — Hierarchical Engineering Agent System  
> **Status:** 🟢 Implemented — Five-Tier Runtime + M3 Judge-Visible Surface (M1 local, M2 Cloud Run, M3 provenance/validation/uncertainty/human-control). Real Gemini 3.5 via Vertex AI + Google ADK 2 integrated (ADR-001/008 fulfilled). 140 tests green.

---

## 🎯 North Star Vision
> **ForgeMind is not a collection of disconnected AI tools for developers.**  
> **It is an autonomous engineering control plane where specialized agents share context, understand relationships across the software lifecycle, reduce operational friction, and know when to act—and when to ask a human.**

---

## 🧩 The Core Problem
AI is accelerating code generation, but writing more code does not help engineering teams:
- Review pull requests with full lifecycle awareness.
- Correlate CI/CD build breakages with recent dependency or code changes.
- Detect subtle documentation drift and specification divergence.
- Prevent alert storms from obscuring root-cause production incidents.
- Maintain an accurate, living understanding of cross-service dependencies.

**Our Core Hypothesis:**
> *As software development accelerates, the bottleneck shifts from code creation to engineering coordination, verification, cross-lifecycle correlation, and system understanding.*

---

## 🏛️ What ForgeMind Is
- **A 5-Tier Hierarchical DAG**: Strict separation of global supervision, domain management, specialist investigation, evidence validation, and decision reduction.
- **An Evidence-Driven Control Plane**: Leaf workers emit structured, verifiable `EvidenceShard`s; cross-domain reconciliation occurs strictly before decisions are made.
- **A Fortified Enterprise Fleet**: Built on Google ADK 2, Vertex AI Gemini 3.5, and Model Armor guardrails, designed for enterprise safety and human escalation.

## 🚫 What ForgeMind Is Not
- **Not another AI code reviewer**: Does not offer superficial line-by-line syntax comments; focuses on cross-lifecycle impact.
- **Not an uncontrolled multi-agent swarm**: Disallows chaotic peer-to-peer agent chatter, circular loops, and unconstrained sub-agent spawning.
- **Not an unverified auto-pilot**: Enforces strict action validation and conservative causality before executing actions or requesting human sign-off.

---

## 🔥 Eight Core Design Principles
1. **Every agent must solve a specific problem**: If removing an agent does not leave a capability gap, it should not exist.
2. **Agents exchange durable evidence, not conversations**: Structured `EvidenceShard`s with provenance citations replace unstructured text chat.
3. **Autonomy is proportional to risk**: Low-risk actions are automated; high-blast-radius actions require human escalation.
4. **Uncertainty is a valid result**: A reliable system knows when evidence is missing and when to escalate.
5. **Understand relationships, not isolated events**: A PR, build failure, deployment, and incident are linked parts of one engineering situation.
6. **A controlled hierarchy beats an uncontrolled swarm**: Strict downward DAG execution (`Supervisor → Managers → Workers → Validator → Reducer`).
7. **Evidence is separated from decisions**: Analysis produces evidence first; reconciliation validates truth; only then does policy produce actions.
8. **No agent has unnecessary authority**: Least privilege per tier; leaf workers have zero spawning authority.

---

## ☁️ Technology Baseline
- **Reasoning Engine**: Gemini 3.5 via Vertex AI
- **Workflow & Orchestration**: Google ADK 2
- **Knowledge Brain**: Notion (authoritative) + ChromaDB (dev-time grounding)
- **Deployment**: Google Cloud Run (Modular Single Application)
