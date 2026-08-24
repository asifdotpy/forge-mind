# ADR-001: Explicit Google Cloud Architecture Mapping

## Status
Accepted

## Date
2026-08-17

## Problem / Context
The All Things Agentic Hackathon stack check is pass/fail. Our system requires explicit mapping of every architectural role to Google Cloud Platform and Agent Development Kit (ADK) services to ensure stack compliance, prevent runtime ambiguity, and resolve naming collisions (such as the distinction between ForgeMind's conceptual Agent Registry profile catalog and Google Cloud's runtime GEAP Agent Registry platform component).

## Decision
Formally map every ForgeMind architectural component to an explicit Google Cloud / ADK service:

| ForgeMind Component | Google Cloud / ADK Service | Purpose |
|---|---|---|
| **Event Ingestion & Sources** | Cloud Pub/Sub + Cloud Run Webhook Receivers | Ingest and normalize external events (GitHub, CI/CD, Slack, Monitoring) |
| **Event Gateway (Acquire)** | Agent Gateway (GEAP) on Cloud Run | Authentication, payload validation against SPEC-001, deduplication |
| **Tier 1 — Engineering Supervisor** | Supervisor Module (Cloud Run) | Global coverage planning (`CoveragePlan`), domain partitioning, execution trace initialization |
| **Tier 2 — 3 Domain Managers** | Manager Modules (Cloud Run) | Bounded domain dispatch, local retry/timeout handling, `DomainFinding` aggregation |
| **Tier 3 — 6 Specialist Workers** | Leaf Worker Modules (Cloud Run) | Specialized evidence production (`EvidenceShard`), zero worker spawning authority |
| **Tier 4 — Cross-Lifecycle Validator** | Validator Module (Cloud Run) | Multi-domain reconciliation, coverage assessment, conservative causality, `ValidatedSituation` |
| **Tier 5 — Decision Reducer & Publisher** | Reducer/Policy Module (Cloud Run) | Risk-bound decision making, `DecisionRecord`, `ProposedAction`, Human Escalation |
| **Shared State & Memory** | Memory Bank (GEAP) + Firestore (planned) | Cross-session state, findings, vector embeddings, entity relationships |
| **Reasoning Model** | Gemini 3.5 via Vertex AI | LLM reasoning, code analysis, and structured extraction across all agent nodes |
| **Agent Framework & Runtime** | Google ADK 2 | Workflow runtime, deterministic orchestration, tool execution, pause/resume gates |
| **Security & Guardrails** | Model Armor + Agent Identity (GEAP) | Content safety filters on untrusted inputs; least-privilege per agent node |
| **Observability** | Agent Observability (GEAP) + OpenTelemetry | End-to-end reasoning-chain traces and provenance tracking |
| **Runtime Discovery** | Agent Registry (GEAP Platform Component) | Runtime discovery and versioning of agent capabilities |

## Consequences
- **Positive**: Direct alignment with Google Cloud judging criteria; zero ambiguity on service boundaries and runtime infrastructure.
- **Trade-offs**: Service selections must be verified during initial runtime scaffolding.
