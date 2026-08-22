# ADR-002: Single Deployable MVP with Replaceable Infrastructure Boundaries

## Status
Accepted

## Context
Deploying each agent tier or worker as an independent microservice introduces network overhead, complex distributed transaction management, deployment friction, and debugging difficulty for the hackathon MVP.

## Decision
Implement the entire ForgeMind v3.0 five-tier hierarchy as clean, modular logical packages inside a single deployable application on Cloud Run. Infrastructure boundaries (LLM calls, vector search, persistent storage) are abstracted behind replaceable interfaces.

## Consequences
- **Positive**: Rapid deployment, zero inter-service network latency, simplified local and cloud testing, unified tracing.
- **Trade-offs**: All tiers scale together in the MVP; individual tiers can be extracted to separate services in future phases if independent scaling is required.
