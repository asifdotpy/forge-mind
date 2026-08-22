# Research: Hierarchical Engineering Agent Runtime DAG

**Feature**: `001-hierarchical-runtime-dag` | **Date**: 2026-08-22

## Purpose

Grounding notes collected from the authoritative Notion Knowledge Base (via the local ChromaDB brain) that inform `spec.md`, `data-model.md`, `plan.md`, and `tasks.md`. Notion remains authoritative for architectural intent; this repository directory is authoritative for executable requirements.

## Source References (Notion)

| Page | ID | Notes |
|------|----|-------|
| ForgeMind — Hierarchical Engineering Agent System | `3be6566c-d850-812b-910c-deb6500bf6c1` | Root; 5-tier DAG overview; v3.0 navigation map |
| BUILD-001 — ForgeMind MVP Implementation Plan | `3c06566c-d850-8119-a28d-ceb5f8edb038` | Repository skeleton, Phase 0→4 milestones, Milestones M1–M3 |
| SPEC-001 — Engineering Situation Contract | `3c06566c-d850-810c-b363-d68f5e26cc91` | Canonical artifact contracts; Phase 0 executable boundary |
| Execution Plan | `3bf6566c-d850-81e4-82ad-dadad4861854` | Phase 0 gate, Phase 1/5/6, Definition of Done |
| ADK-001 — ForgeMind ADK 2 Workflow Runtime | `3c36566c-d850-8156-bbe4-ebd80f6041d9` | ADK 2 mapping; revised implementation sequence |
| FIXTURE-001 — Change-to-Incident Canonical Demo | `3c06566c-d850-812b-90c9-d832f3785458` | Golden Demo (distinct from repo fixtures) |

## Key Findings

### 1. Authority boundaries (confirmed by SPEC-001 + Execution Plan)
- Notion = authoritative for product vision, architecture, ADRs, agent intent, evaluation design, invariants.
- `specs/001-hierarchical-runtime-dag/` = authoritative for executable requirements, machine-readable schemas, fixtures, `plan.md`, `tasks.md`.

### 2. Canonical artifact set (frozen in Phase 0)
Event, CoveragePlan, EvidenceShard, DomainFinding, ValidatedSituation, DecisionRecord, ProposedAction, ActionValidation, Escalation.
No tier or terminology changes allowed in Phase 0.

### 3. Tier constraints (from constitution + SPEC-001)
- Tier 1 Supervisor → CoveragePlan before dispatch.
- Tier 2 Managers → aggregate only within their domain.
- Tier 3 Workers → bounded evidence shards, never decisions, never spawn children.
- Tier 4 Validator → ValidatedSituation + explicit coverage gaps + conservative causality.
- Tier 5 Reducer → DecisionRecord / ProposedAction from a ValidatedSituation only.
- Action Validation and Action/Escalation are downstream stages, **not** additional tiers.

### 4. Provenance invariants
- `DomainFinding` references exact `evidence_shard_ids`.
- `ValidatedSituation` references `finding_ids` + supporting/conflicting evidence.
- `DecisionRecord` references exactly one `validated_situation_id`.
- `ProposedAction` references its `decision_id`; `ActionValidation` references its `action_id`.
- `Escalation` preserves the unresolved situation, decision, uncertainty, and triggering rule.
- Missing evidence / uncontactable domains → explicit `missing_domains`.

### 5. Fixture policy
- Repository fixtures are Event envelopes: scenario data inside `Event.payload`, with separate expected assertions.
- Phase 0 fixtures use names `FIXTURE-001-happy-path.json` and `FIXTURE-002-escalation.json`.
- Not to be confused with the Notion Golden Demo `FIXTURE-001` (Change-to-Project-Change demo).

## Open Questions / Tracked Dependencies
- ADK 2 runtime design is a separate addendum (ADK-001). Phase 0 is fixture/CLI-backed; external webhooks deferred.
- Full worker set is Phase 4 after the MVP vertical slice passes.

## Confidence
Queries against ChromaDB `forgemind_v3_core` (synced 2026-08-21) returned consistent source chunks for all above claims; no conflicting evidence found.