# ForgeMind System Constitution

## 1. Core Operating Philosophy & Authority Model
- **Notion Knowledge Base**: Authoritative source for system vision, architectural intent, Architecture Decision Records (ADRs), and high-level boundaries.
- **Spec-Kit & Repository (`docs/specs/`)**: Authoritative source for executable specifications, canonical data models, JSON Schema contracts, test fixtures, implementation plans, and atomic task graphs.
- **Spec-Driven Engineering**: No agent or application code shall be written without an approved, verified specification in `docs/specs/`.

## 2. Five-Tier Hierarchical DAG Architecture
Execution flows strictly downward along the five-tier Directed Acyclic Graph. Cyclical dependencies between agents are strictly prohibited.

```
┌─────────────────────────────────────────────────────────────┐
│ Tier 1: Engineering Supervisor                              │
│ • Owns global lifecycle coordination & trace initialization │
│ • Dispatches bounded execution plans to Domain Managers     │
│ • Never executes leaf-level domain analysis                 │
├─────────────────────────────────────────────────────────────┤
│ Tier 2: Domain Manager                                      │
│ • Owns domain partition (Code, Delivery, Reliability)       │
│ • Dispatches and manages Specialist Workers                 │
│ • Aggregates shards into DomainFindings                     │
│ • Never performs cross-domain reconciliation                │
├─────────────────────────────────────────────────────────────┤
│ Tier 3: Specialist Worker                                   │
│ • Leaf worker executing focused analysis                    │
│ • Emits EvidenceShards with source citations                │
│ • Never spawns child agents; never makes policy decisions   │
├─────────────────────────────────────────────────────────────┤
│ Tier 4: Cross-Lifecycle Validator                           │
│ • Reconciles multi-domain findings into ValidatedSituations │
│ • Identifies correlations vs causality explicitly           │
│ • Highlights missing or conflicting evidence                │
│ • Never emits autonomous actions                            │
├─────────────────────────────────────────────────────────────┤
│ Tier 5: Decision Reducer & Publisher                        │
│ • Evaluates ValidatedSituation against Decision Policy      │
│ • Emits DecisionRecord (INFO, WARN, BLOCKING, Escalation)   │
│ • Emits ProposedAction (subject to Action Validation)       │
│ • Never consumes raw worker output directly                 │
└─────────────────────────────────────────────────────────────┘
```

## 3. Downstream Post-Decision Pipeline
Action Validation and Action/Escalation execution are downstream verification stages, **not** additional agent tiers:
$$\text{DecisionRecord} \longrightarrow \text{ProposedAction} \longrightarrow \text{ActionValidation} \longrightarrow \text{Action Execution } \mathbf{OR} \text{ Human Escalation}$$

## 4. Invariant Rules of Provenance & Evidence
1. **Separation of Evidence and Decisions**: Workers produce evidence; only the Reducer produces decisions.
2. **Strict Provenance Trail**:
   - `DomainFinding` must reference the exact `source_shard_ids`.
   - `ValidatedSituation` must reference `source_finding_ids`, `supporting_evidence_ids`, and `conflicting_evidence_ids`.
   - `DecisionRecord` must reference exactly one `situation_id`.
   - `ProposedAction` must reference its `decision_id`.
   - `ActionValidation` must reference its `proposed_action_id`.
   - `Escalation` must preserve the unresolved situation, decision, uncertainty, and triggering rule.
3. **Causality Rigor**: Co-occurring events across domains cannot be claimed as causal without explicit supporting evidence (`causality_assessment`).
4. **Visibility of Absence**: Missing evidence or uncontactable domains must be explicitly represented in `missing_domains` and factored into escalation policies.
