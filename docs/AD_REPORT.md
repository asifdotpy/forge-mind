# Autonomous Decision Accuracy Report

**Date:** 2026-08-28  
**System:** ForgeMind v3.0 — Evidence-Aware Autonomous Decisioning (ADR-011)  
**Live endpoint:** https://forgemind-n3nupsii5a-uc.a.run.app  
**Commit:** `c012fa7`

---

## Summary

| Metric | Value |
|--------|-------|
| Total PRs evaluated | 28 |
| `safe_autonomous` | 0 (0%) |
| `human_review` | 28 (100%) |
| `escalate` | 0 (0%) |

## Distribution

```
safe_autonomous:  0 ( 0%) ████████████████████
human_review:    28 (100%) ████████████████████
escalate:         0 ( 0%) ████████████████████
```

## Per-PR Results

| PR | Title | Autonomy | Confidence | Causality | Actions |
|----|-------|----------|------------|-----------|---------|
| #210 | docs(claims): reconcile scopes | human_review | 0.79 | correlated | comment |
| #204 | build(deps): bump actions/checkout | human_review | 0.75 | correlated | comment |
| #203 | Q2 Milestone Verification | human_review | 0.81 | correlated | comment |
| #195 | Roadmap Status Analysis | human_review | 0.85 | correlated | comment |
| #194 | Agent Security Problem Synthesis | human_review | 0.85 | correlated | comment |
| #193 | Web Oracle Bridge | human_review | 0.82 | correlated | comment |
| #192 | Robust Containerization | human_review | 0.79 | correlated | comment |
| #191 | Containerization: Dockerfile | human_review | 0.79 | correlated | comment |
| #190 | Containerize Vertex Sentinel | human_review | 0.79 | correlated | comment |
| #189 | Restore Institutional UI | human_review | 0.85 | correlated | comment |
| #185 | Institutional UI Overhaul | human_review | 0.82 | correlated | comment |
| #180 | Investor Video Preparation | human_review | 0.82 | correlated | comment |
| #179 | TradingAgents Competitive Analysis | human_review | 0.81 | correlated | comment |
| #177 | Institutional Investor Package | human_review | 0.85 | correlated | comment |
| #169 | Risk Validation Pipeline | human_review | 0.85 | correlated | comment |
| #154 | Mainnet V1.0 Readiness | human_review | 0.82 | correlated | comment |
| #151 | Update Public Release Evaluation | human_review | 0.85 | correlated | comment |
| #125 | bump viem | human_review | 0.85 | correlated | comment |
| #124 | bump hardhat-verify | human_review | 0.85 | correlated | comment |
| #123 | bump hardhat | human_review | 0.85 | correlated | comment |
| #122 | bump hardhat-network-helpers | human_review | 0.85 | correlated | comment |
| #121 | bump hardhat-ignition-ethers | human_review | 0.85 | correlated | comment |
| #120 | bump hardhat-viem | human_review | 0.85 | correlated | comment |
| #119 | bump hardhat-ignition | human_review | 0.85 | correlated | comment |
| #118 | bump ignition-core | human_review | 0.85 | correlated | comment |
| #117 | bump firestore | human_review | 0.85 | correlated | comment |
| #116 | bump hardhat-ethers | human_review | 0.85 | correlated | comment |
| #115 | bump actions/setup-node | human_review | 0.85 | correlated | comment |

---

## Analysis

### Why 100% human_review?

The webhook payload only contains `changed_files`. This means:

- **Code worker** (pr-pre-flight-ast-worker): OBSERVED — it can see the files
- **Docs worker**: NO_SIGNAL — no `docs_summary` in payload
- **Build worker**: NO_SIGNAL — no `ci_outcome` in payload
- **Alert worker**: NO_SIGNAL — no `alert_signals` in payload
- **Telemetry worker**: NO_SIGNAL — no `telemetry_signals` in payload
- **Security worker**: NO_SIGNAL — no `dependency_scan` in payload

**Evidence strength:** 1/6 workers with OBSERVED evidence ≈ 0.17 (below the 0.33 low-risk threshold).

The system correctly identifies this as insufficient evidence and escalates to human review.

### Is this the right behavior?

**Yes.** The system is working as designed:

1. It does NOT fake confidence — confidence is high (0.75-0.85) but evidence is weak
2. It does NOT average away the missing evidence — evidence strength is computed separately
3. It DOES ask a human when it doesn't have enough information to act autonomously

This is the **conservative-by-design** behavior that ADR-011 mandates.

### What would enable autonomy?

To reach `safe_autonomous` for real PRs, the webhook payload needs to carry:

- CI status (pass/fail) → build worker can make OBSERVED claims
- Dependency scan results → security worker can make OBSERVED claims
- Docs drift signals → docs worker can make OBSERVED claims
- Deployment status → production worker can make OBSERVED claims

With enriched payloads, evidence strength would increase and the system could legitimately reach `safe_autonomous` for well-evidenced PRs.

---

## Honest Assessment

### What's working

- The evidence-aware decisioning system correctly constrains autonomy when evidence is weak
- All 28 PRs are held for human review — no false autonomous approvals
- The system is transparent about its uncertainty (evidence_strength, causality_status)
- The escalation safety net is functioning correctly

### What's not yet demonstrated

- The system has NOT been tested with enriched payloads that would enable `safe_autonomous`
- The 0% autonomy rate reflects the limited webhook payload, not a failure of the decisioning logic
- To demonstrate `safe_autonomous`, the webhook needs to carry CI/security/docs data

### Recommendation for Demo

The demo should show:

1. **Current behavior:** PR with only `changed_files` → `human_review` (conservative, correct)
2. **Future behavior:** PR with enriched payload (CI pass + security scan + docs updated) → `safe_autonomous` (if evidence is strong enough)
3. **The story:** "ForgeMind doesn't guess. When it has enough evidence, it acts. When it doesn't, it asks a human."

This is a **stronger** demo story than showing autonomous approval of a dependabot PR. It demonstrates the system's judgment, not just its automation.

---

## Conclusion

The evidence-aware decisioning system is working correctly. The 100% human_review rate is the expected behavior given the limited webhook payload. The system is conservative, transparent, and safe.

To demonstrate `safe_autonomous` in the demo, enrich the webhook payload with CI status, security scan results, and docs drift signals. Then re-measure.

---

**Report prepared by:** SpecForge (ForgeMind verification agent)  
**Status:** Complete
