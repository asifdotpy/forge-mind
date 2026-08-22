# ADR-004: Workers Emit Durable Evidence Shards, Not Conversational Text

## Status
Accepted

## Context
Natural language conversational exchanges between agents introduce prompt drift, loss of factual precision, and untraceable claims.

## Decision
Specialist workers must emit structured, durable `EvidenceShard` payloads containing observations, verified claims, citations/source references, confidence scores, and uncertainty annotations.

## Consequences
- **Positive**: Machine-verifiable reasoning, full provenance trails, and reproducible validation.
- **Trade-offs**: Workers must structure their findings according to strict JSON Schema contracts.
