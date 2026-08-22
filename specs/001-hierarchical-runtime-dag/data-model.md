# Data Model: Hierarchical Engineering Agent Runtime DAG

**Feature**: `001-hierarchical-runtime-dag` | **Date**: 2026-08-22

## 1. Object Flow (canonical lineage)

```plain text
Event
  → CoveragePlan          (Tier 1 Supervisor)
  → EvidenceShard         (Tier 3 Worker, per domain)
  → DomainFinding         (Tier 2 Manager, per domain)
  → ValidatedSituation    (Tier 4 Cross-Lifecycle Validator)
  → DecisionRecord        (Tier 5 Decision Reducer & Publisher)
  → ProposedAction        (Tier 5)
  → ActionValidation      (downstream safety gate)
  → Action OR Escalation  (terminal)
```

Every derived artifact MUST carry:
- `situation_id` (stable correlation key)
- `provenance` / upstream ID references
- `execution_trace_id` (root trace) where applicable

## 2. Entity Relationship Diagram (dependency view)

```text
Event ──────────────────────────┐
  │ supplies context            │
  ▼                             │
CoveragePlan ──selects──► Domain Manager(s) ──spawns──► Specialist Worker(s)
  │                                                          │
  │                                                          └─► EvidenceShard
  │                                                                 ▲
  └───────────────────────────────────►  DomainFinding ◄── aggregates │
  DomainFinding ──feeds──► CrossLifecycleValidator ──► ValidatedSituation
                                                        │
                                                        ▼
                                                  DecisionReducer ──► DecisionRecord
                                                                          │
                                                                          ▼
                                                                    ProposedAction
                                                                          │
                                                                          ▼
                                                                  ActionValidation ──► Action OR Escalation
```

## 3. Attribute Contracts (summary; see `contracts/*.schema.json`)

### 3.1 Event
- `event_id`, `situation_id`, `type` (`pr|ci_failure|deployment|incident|notification|documentation|security`)
- `source` (`github|ci|monitoring|fixture`), `summary`, `timestamp` (ISO-8601), `reference`
- `affected_entities[]`, `provenance`; fixtures add `payload` (envelope scenario data)

### 3.2 CoveragePlan (Tier 1)
- `coverage_plan_id`, `situation_id`, `selected_domains` (`code|delivery|production`)
- `selected_managers[]`, `selected_workers[]`, `selection_rationale[]`
- `excluded_workers[]`, `coverage_requirements{}`, `global_constraints{}`
- `expected_artifacts[]`, `provenance{}`, `execution_trace_id`

### 3.3 EvidenceShard (Tier 3)
- `evidence_shard_id`, `situation_id`, `worker`, `domain`
- `observations[]`, `claims[]`, `evidence_ids[]`, `confidence` (0..1)
- `risk_level` (`low|medium|high|critical`), `uncertainties[]`
- `affected_entities[]`, `provenance{}`, `execution_trace_id`

### 3.4 DomainFinding (Tier 2)
- `finding_id`, `situation_id`, `domain`, `evidence_shard_ids[]`
- `summary`, `supported_claims[]`, `conflicts[]`, `coverage{}`
- `confidence`, `uncertainties[]`

### 3.5 ValidatedSituation (Tier 4)
- `validated_situation_id`, `situation_id`, `finding_ids[]`, `evidence_ids[]`
- `supporting_evidence[]`, `conflicting_evidence[]`, `coverage{}`
- `deduplication[]`, `correlations[]`, `causality_status` (`unsupported|correlated|supported|verified`)
- `confidence`, `uncertainties[]`, `validation_notes[]`

### 3.6 DecisionRecord (Tier 5)
- `decision_record_id`, `validated_situation_id`, `decision`
- `rationale[]`, `risk_level`, `autonomy_class` (`safe_autonomous|human_review|escalate`)
- `confidence`, `uncertainties[]`, `requires_human`

### 3.7 ProposedAction (Tier 5)
- `action_id`, `decision_id`, `action`, `risk_level`
- `required_authority`, `status` (`proposed|validated|rejected|executed|escalated`)

### 3.8 ActionValidation (downstream gate)
- `validation_id`, `action_id`, `policy_result` (`allowed|requires_human|rejected`)
- `checks[]`, `reason`, `validated_at` (ISO-8601)

### 3.9 Escalation (terminal for unsafe/uncertain)
- `escalation_id`, `situation_id`, `reason` (`uncertainty|risk|coverage_gap|policy_boundary|validation_failure`)
- `summary`, `required_human_role`, `evidence_ids[]`

## 4. Situation Lifecycle (state machine)

```text
open → analyzing → reconciling → decision_ready → action_validation → resolved
                                                                      ↘ escalated
                                                                      ↘ closed_inconclusive
```

### State transitions
| From | To | Transition |
|------|----|-----------|
| open | analyzing | Event accepted & CoveragePlan emitted |
| analyzing | reconciling | DomainFindings aggregated |
| reconciling | decision_ready | ValidatedSituation produced |
| decision_ready | action_validation | DecisionRecord + ProposedAction |
| action_validation | resolved | Action validated & executed |
| action_validation | escalated | Validation fails / human required |
| decision_ready | closed_inconclusive | Insufficient evidence / coverage gap |

## 5. Invariants

1. Workers never determine final decisions.
2. Managers aggregate only within their bounded domain.
3. Only Tier 4 creates `ValidatedSituation`; only Tier 5 creates operational decisions.
4. Confidence ≠ proof; uncertainty is always preserved.
5. Correlation never presented as causation without explicit `causality_assessment`.
6. Every proposed action passes Action Validation before execution; otherwise Escalate.
7. Provenance is unbroken (every downstream artifact references its exact upstream IDs).