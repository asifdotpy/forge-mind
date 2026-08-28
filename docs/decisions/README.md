# Architecture Decision Records (ADRs)

ADRs document significant architectural, technical, and structural decisions made in ForgeMind to prevent recurring debates and settled question reopening.

## Canonical v3.0 ADR Catalog

| ADR | Title | Status | Scope |
|---|---|---|---|
| [**ADR-001**](file:///home/asif1/forge-mind/docs/decisions/ADR-001-google-cloud-architecture-mapping.md) | Explicit Google Cloud Architecture Mapping | Accepted | GCP services, Vertex AI Gemini 3.5, ADK, GEAP |
| [**ADR-002**](file:///home/asif1/forge-mind/docs/decisions/ADR-002-single-deployable-mvp.md) | Single Deployable MVP with Replaceable Infrastructure Boundaries | Accepted | Modular single Cloud Run container |
| [**ADR-003**](file:///home/asif1/forge-mind/docs/decisions/ADR-003-five-tier-hierarchical-dag.md) | Adopt a Five-Tier Hierarchical DAG | Accepted | Supervisor → Managers → Workers → Validator → Reducer |
| [**ADR-004**](file:///home/asif1/forge-mind/docs/decisions/ADR-004-durable-evidence-shards.md) | Workers Emit Durable Evidence Shards | Accepted | Structured `EvidenceShard`s over natural language chat |
| [**ADR-005**](file:///home/asif1/forge-mind/docs/decisions/ADR-005-cross-lifecycle-validation-tier.md) | Cross-Lifecycle Validation Is a Dedicated Tier | Accepted | Tier 4 multi-domain reconciliation & causality |
| [**ADR-006**](file:///home/asif1/forge-mind/docs/decisions/ADR-006-separate-decision-reduction.md) | Separate Decision Reduction from Investigation | Accepted | Tier 5 policy evaluation & proposed actions |
| [**ADR-007**](file:///home/asif1/forge-mind/docs/decisions/ADR-007-dag-and-leaf-worker-constraints.md) | Enforce DAG Invariants and Leaf-Worker Constraints | Amended (2026-08-24) | Leaf workers cannot spawn sub-agents; no cycles; lineage via schema-required provenance, `TRC-*` root trace where contracted; distributed tracing via OTel in Phase 10 |
| [**ADR-008**](file:///home/asif1/forge-mind/docs/decisions/ADR-008-adk-2-workflow-runtime.md) | Adopt Google ADK 2 as the ForgeMind Workflow Runtime | Accepted | ADK 2 deterministic orchestration & human gates |
| [**ADR-009**](file:///home/asif1/forge-mind/docs/decisions/ADR-009-chromadb-development-time-boundary.md) | ChromaDB Is a Development-Time Derived Index | Accepted | Dev-time Knowledge Brain; never runtime state |
| [**ADR-010**](file:///home/asif1/forge-mind/docs/decisions/ADR-010-m3-ai-core-scope.md) | M3 AI Core Scope — Real Gemini 3.5 via Vertex AI inside bounded ADK 2 nodes | Accepted | Bounded Gemini 3.5 + ADK 2 workflow runtime |
| [**ADR-011**](file:///home/asif1/forge-mind/docs/decisions/ADR-011-evidence-aware-decisioning.md) | Evidence-Aware Autonomous Decisioning | Accepted | No confidence upgrade on evidence state; risk-adaptive confidence |
| [**ADR-012**](file:///home/asif1/forge-mind/docs/decisions/ADR-012-realworld-deployment-surroundings.md) | Real-World Deployment Surroundings (Connector Layer, CI/CD, Secret Manager) | Candidate (2026-08-28) | Connector isolation, auto-deploy, secret zero-trust |

## ADR Template
```markdown
# ADR-XXX: [Title]

## Status
[Draft | Accepted | Superseded | Deprecated]

## Context
What problem or technical decision are we facing? What constraints exist?

## Decision
What specific technical choice did we make?

## Alternatives Considered
- Option A: ... (Why rejected)
- Option B: ... (Why rejected)

## Consequences
- Positive: ...
- Negative / Trade-offs: ...
```
