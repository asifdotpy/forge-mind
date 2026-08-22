# SPEC-001: Hierarchical Engineering Agent Runtime DAG

## Status: In Progress

## 1. Overview & Purpose
SPEC-001 defines the canonical v3.0 contract for ForgeMind’s hierarchical DAG execution lifecycle: `Acquire → Analyze → Reconcile → Produce → Validate`. It standardizes the evidence and decision object flow, provenance rules, tier responsibilities, and acceptance criteria so implementation remains deterministic, inspectable, and review-gated.

## 2. Inputs & Preconditions
- `.specify/constitution.md` is present and v3.0-aligned.
- Notion remains authoritative for architectural intent and ADRs.
- `docs/specs/` defines spec lifecycle and template conventions.
- `CURRENT_STATE.md` indicates Phase 0 is the pre-implementation gate.

## 3. Outputs & Public Contract

### 3.1 Canonical Runtime Lifecycle
```plain text
Acquire → Analyze → Reconcile → Produce → Validate
```

### 3.2 Canonical Object Flow
```plain text
Event
  → CoveragePlan
  → EvidenceShard
  → DomainFinding
  → ValidatedSituation
  → DecisionRecord
  → ProposedAction
  → ActionValidation
  → Action OR Escalation
```

### 3.3 Event Contract
```json
{
  "event_id": "string",
  "situation_id": "string",
  "type": "pr|ci_failure|deployment|incident|notification|documentation|security",
  "source": "github|ci|monitoring|fixture",
  "summary": "string",
  "timestamp": "ISO-8601",
  "reference": "stable identifier or URL",
  "affected_entities": [],
  "provenance": {}
}
```

### 3.4 CoveragePlan Contract
Produced only by Tier 1 — Engineering Supervisor.
```json
{
  "coverage_plan_id": "string",
  "situation_id": "string",
  "selected_domains": ["code|delivery|production"],
  "selected_managers": [],
  "selected_workers": [],
  "selection_rationale": [],
  "excluded_workers": [],
  "coverage_requirements": {},
  "global_constraints": {},
  "expected_artifacts": [],
  "provenance": {},
  "execution_trace_id": "string"
}
```

### 3.5 EvidenceShard Contract
Produced by Tier 3 Specialist Workers.
```json
{
  "evidence_shard_id": "string",
  "situation_id": "string",
  "worker": "string",
  "domain": "code|delivery|production",
  "observations": [],
  "claims": [],
  "evidence_ids": [],
  "confidence": 0.0,
  "risk_level": "low|medium|high|critical",
  "uncertainties": [],
  "affected_entities": [],
  "provenance": {},
  "execution_trace_id": "string"
}
```

### 3.6 DomainFinding Contract
Produced by Tier 2 Domain Managers.
```json
{
  "finding_id": "string",
  "situation_id": "string",
  "domain": "code|delivery|production",
  "evidence_shard_ids": [],
  "summary": "string",
  "supported_claims": [],
  "conflicts": [],
  "coverage": {},
  "confidence": 0.0,
  "uncertainties": []
}
```

### 3.7 ValidatedSituation Contract
Produced only by Tier 4 — Cross-Lifecycle Validator.
```json
{
  "validated_situation_id": "string",
  "situation_id": "string",
  "finding_ids": [],
  "evidence_ids": [],
  "supporting_evidence": [],
  "conflicting_evidence": [],
  "coverage": {},
  "deduplication": [],
  "correlations": [],
  "causality_status": "unsupported|correlated|supported|verified",
  "confidence": 0.0,
  "uncertainties": [],
  "validation_notes": []
}
```

### 3.8 DecisionRecord Contract
Produced only by Tier 5 — Decision Reducer & Publisher.
```json
{
  "decision_record_id": "string",
  "validated_situation_id": "string",
  "decision": "string",
  "rationale": [],
  "risk_level": "low|medium|high|critical",
  "autonomy_class": "safe_autonomous|human_review|escalate",
  "confidence": 0.0,
  "uncertainties": [],
  "requires_human": true
}
```

### 3.9 ProposedAction Contract
```json
{
  "action_id": "string",
  "decision_id": "string",
  "action": "string",
  "risk_level": "low|medium|high|critical",
  "required_authority": "string",
  "status": "proposed|validated|rejected|executed|escalated"
}
```

### 3.10 ActionValidation Contract
```json
{
  "validation_id": "string",
  "action_id": "string",
  "policy_result": "allowed|requires_human|rejected",
  "checks": [],
  "reason": "string",
  "validated_at": "ISO-8601"
}
```

### 3.11 Escalation Contract
```json
{
  "escalation_id": "string",
  "situation_id": "string",
  "reason": "uncertainty|risk|coverage_gap|policy_boundary|validation_failure",
  "summary": "string",
  "required_human_role": "string",
  "evidence_ids": []
}
```

### 3.12 Situation State
```plain text
open
→ analyzing
→ reconciling
→ decision_ready
→ action_validation
→ resolved
```

Alternative terminal states:
```plain text
escalated
closed_inconclusive
```

## 4. Acceptance Criteria
- [ ] Every investigation has one stable `situation_id`.
- [ ] Every derived artifact retains provenance and upstream references.
- [ ] Workers provide bounded evidence and cannot determine final decisions.
- [ ] Domain Managers may aggregate only within their bounded domain.
- [ ] Only the Cross-Lifecycle Validator creates a `validated_situation`.
- [ ] Only the Decision Reducer converts a validated situation into an operational decision.
- [ ] Confidence is not proof; uncertainty remains explicit.
- [ ] Correlation is never represented as confirmed causation without supporting evidence.
- [ ] Every proposed action passes the Action Validation boundary.
- [ ] High-uncertainty or insufficiently supported actions produce escalation.

## 5. Verification Plan
- Automated contract test command: `pytest tests/contract/`
- Integration verification command: `pytest tests/integration/`
- Fixture-backed CLI execution for Phase 0 contracts: `python scripts/run_fixture.py fixtures/inputs/FIXTURE-001.json`
- Black-box verification command: `python scripts/query_brain.py --scenario FIXTURE-001`

## 6. Source Alignment
- Source of truth: Notion `BUILD-001` + Notion `SPEC-001`.
- Repository authority: `specs/001-hierarchical-runtime-dag/`.
- Notion authority: architecture, ADRs, architectural intent, invariants.

## 7. Non-Goals
- Autonomous merge or production deployment.
- Perfect causal inference.
- Production-scale knowledge graph.
- Recursive worker spawning.
- Unbounded peer-to-peer agent communication.

## 8. Required Contract Tests
- valid event creation
- provenance preservation
- evidence-shard validation
- manager aggregation boundaries
- multi-domain validation
- coverage-gap detection
- correlation-vs-causation handling
- decision requires validated situation
- action validation enforcement
- escalation generation
- uncertainty preservation

## 9. Phase 0 Fixture Policy
- `FIXTURE-001`: canonical Event-envelope happy path with separate expected assertions.
- `FIXTURE-002`: canonical Event-envelope escalation path with separate expected assertions.
- Existing Change-to-Incident Golden Demo remains distinct and must not be conflated with Phase 0 contract fixtures.

## 10. Stop Condition
Complete this SPEC-001, the related data-model/plan/tasks artifacts, and repository scaffolding; then stop for review before implementing runtime tiers.

**Status:** In Progress — implementation-ready pending Phase 0 review.
