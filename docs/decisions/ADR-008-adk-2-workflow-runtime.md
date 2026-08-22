# ADR-008: Adopt Google ADK 2 as the ForgeMind Workflow Runtime

## Status
Accepted

## Date
2026-08-21

## Problem / Context
Executing the locked v3.0 five-tier hierarchy requires deterministic stage transitions, concurrent domain branches, durable pause/resume for human escalation, callback freshness checks, and long-running continuation support. Pure agent-directed orchestration without a formal workflow engine risks non-deterministic stage skipping and fragile state management.

## Decision
Adopt **Google ADK 2** as the workflow runtime and orchestration substrate for ForgeMind v3.0 while strictly preserving the five-tier hierarchy and its authority boundaries:
- ADK 2 manages deterministic workflow orchestration, state graphs, pause/resume, and human approval gates.
- Bounded LLM agents (powered by Vertex AI Gemini 3.5) execute specialized engineering judgment inside designated workflow nodes.
- Downstream safety validations and callback verifications are enforced as workflow gate nodes before actions execute.

## Consequences
- **Positive**: Deterministic execution flow, production-grade pause/resume for human approvals, seamless integration with Google Cloud GenAI observability.
- **Trade-offs**: Requires structuring agent invocations as bounded nodes within the ADK 2 workflow DAG.
