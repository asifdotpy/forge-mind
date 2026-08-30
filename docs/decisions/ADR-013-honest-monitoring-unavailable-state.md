# ADR-013: Honest Monitoring Unavailable State

## Status

Draft

## Date

2026-08-30

## Problem / Context

Gap analysis (`/home/asif1/tmp/MONITORING_GAP.md`) established that the monitoring
evidence path fails OPEN today:

- `monitoring_search.py:70-72` and `:143-145` return `{"alerts": [], "telemetry": []}`
  on any failure (missing ADK, query error, or unset credentials).
- `enrichment.py:430-431` and `:545-546` re-wrap the same fail-open behaviour with
  `try/except -> []`.

As a result, *no monitoring source configured*, *the search errored*, and
*the search ran and genuinely found nothing* are indistinguishable empty lists.

That makes "no incident" a claim that cannot be audited: a worker with no
incident feed emits `NO_SIGNAL` ("worker looked, found nothing"), which
turns the positive-evidence rule in ADR-011 into an absence-of-capability
rather than absence-of-incidents.

## Decision

1. **Monitoring sources report a status channel.** `MonitoringSearchService`
   returns `{state: "ok", alerts, telemetry}` when a real query succeeded (even
   with zero results) and `{state: "unavailable", alerts: [], telemetry: []}`
   when no source is configured, no credentials exist, or the query errored.
2. **`UNAVAILABLE` is a distinct evidence state** — already defined at
   `validator.py:100` — and is emitted by the alert/telemetry workers whenever
   `monitoring_state == "unavailable"` is present in their worker context.
   It is never conflated with `NO_SIGNAL`.
3. **`UNAVAILABLE` is never positive evidence.** `_compute_evidence_strength`
   (`validator.py:772-860`) already counts only `observed`/`verified`; extending
   it to a real `UNAVAILABLE` claim requires no ratio change.
4. **`UNAVAILABLE` blocks autonomous action.** The reducer downgrades any
   `safe_autonomous` candidate to `human_review` when any contributing domain
   carries `UNAVAILABLE` evidence: a dimension that cannot be assessed must not
   be assumed safe. This adopts the fail-closed-to-cannot-assess principle.

## Alternatives Considered

- **Keep fail-open to empty lists.** Rejected: it silently converts absence of
  capability into absence of incidents, which violates ADR-011's evidence
  quality rules and over-states confidence in the negative.
- **Force `escalate` on `UNAVAILABLE`.** Rejected: escalation should be
  reserved for active risk (confidence below threshold / conflicts); a missing
  data source is a review-gate condition, not an emergency.
- **Invent a fourth status (e.g. `degraded`).** Rejected: over-modeling;
  `ok`/`unavailable` covers the observable cases today.

## Consequences

### Positive
- Monitoring evidence becomes auditable: a reader can tell "queried, was clean"
  from "could not be assessed".
- Autonomy is correctly constrained when a dimension cannot be assessed.
- The dashboard already renders an honest "No data" path
  (`dashboard/sections.py:420`) that can surface `UNAVAILABLE` without fabrication.

### Trade-offs / Risks
- Autonomy rate decreases for environments without a configured monitoring
  source (e.g. local dev): alert/telemetry workers now produce `UNAVAILABLE`
  instead of `NO_SIGNAL`, which downgrades `safe_autonomous` to `human_review`.
  This is intentional and honest.
- Phrase-based detection is duplicated between `workers._build_structured_claims`
  and `validator._aggregate_evidence_states`; kept in sync deliberately (mirrors
  the existing `no_signal` phrase duplication).

## Verification

- Contract tests updated in `tests/contract/test_monitoring_search.py` to assert
  the `state` channel on both success and failure.
- New tests assert alert/telemetry workers emit `evidence_state == "unavailable"`
  when `monitoring_state == "unavailable"`, and that the reducer returns
  `human_review` (never `safe_autonomous`) in that case.