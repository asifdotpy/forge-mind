# ADR-014: File-Derived Domain Selection for PR Events

## Status

Draft

## Date

2026-08-30

## Problem / Context

Gap analysis (`/home/asif1/tmp/DOMAIN_MAPPING_GAP.md`) established that domain
selection for PR events is content-blind:

- `acquisition.py:78-86` maps the `pr` event type to `("code",)` only — a PR
  touching `.github/workflows/*` is classified identically to a docs-only PR.
- There is no file-to-domain classifier anywhere in `src/` (grep confirmed).
- The webhook masks the gap by brute force: `enrichment.py:484` hardcodes
  `affected_domains: ["code", "delivery", "production"]` for every PR (and
  `adk_routes.py:488-496` adds a decorative top-level `selected_domains` that
  `_select_domains` never reads).

Net effect: coverage is constant (always 100%) for webhook PRs, so
`missing_domains` (`validator.py:188-221`) is always `[]` and cannot surface
actual gaps.

SPEC-001 (`spec.md:24-30`) requires the Supervisor to "determine which lifecycle
domains are affected" and emit a CoveragePlan that reflects the event, not a
fixed set.

## Decision

1. **Domain selection for `pr` events is derived from the changed files.**
   `acquisition._select_domains` gains a file-path classifier so a PR touching
   CI/CD configuration selects `delivery`, and a security-sensitive path can
   select `production`.
2. **Canonical mapping (implementation):**
   - `.github/workflows/*`, `Jenkinsfile`, `.gitlab-ci.yml`, `.github/*.yml`
     (workflow metadata), and other CI/CD config -> `delivery`.
   - `docs/`, `*.md`, `*.rst`, `*.txt` (documentation) -> `code`.
   - `auth/`, `security/`, `*.pem`, `*.key`, `secrets/*`, `Dockerfile` (when
     under a security/trust boundary) -> `production` (defensible; see below).
   - Any other source file -> `code` (default).
3. **The webhook stops brute-forcing all three domains.** `enrichment.py` and
   `adk_routes.py` stop hardcoding `affected_domains`/`selected_domains`; the
   classifier runs on the actual changed files and the CoveragePlan reflects
   them, making `missing_domains` meaningful again.
4. **`payload.affected_domains` remains an explicit override** (callers may
   still declare intent); the classifier is the default for PRs when the
   override is absent.

## Alternatives Considered

- **Keep the event-type default map.** Rejected: it cannot distinguish a
  docs PR from a CI-PR; both are type `pr`.
- **Force all three domains always (current webhook behavior).** Rejected: it
  makes coverage uninformative and sends delivery/production workers to produce
  NO_SIGNAL/empty evidence for purely-doc PRs, deflating evidence strength.
- **LLM-based classification.** Rejected: non-deterministic; violates the
  replay-stable CoveragePlan invariant (`acquisition.py:33-34`).

## Consequences

### Positive
- Coverage reflects the actual event: a CI-file PR selects `delivery` (+`code`),
  so `missing_domains` becomes meaningful and the validator's latent
  workflow-gap check (`validator.py:753-763`) can finally fire.
- Evidence strength is not deflated by sending irrelevant workers at every PR.
- Deterministic and replay-stable.

### Trade-offs / Risks
- Some PRs now have fewer selected domains, so fewer delivery/production workers
  run. This is correct: a docs-only PR no longer pretends to assess delivery.
- Classification is heuristic (path patterns). Paths it mistakes can be fixed
  by extending the mapping; the decision is documented here.
- A docs-only delivery PR that touches `docs/` but intends a delivery change
  would be `code`-only. Acceptable: intent is not inferable from paths alone;
  `payload.affected_domains` remains an explicit override.

## Verification

- Contract tests in `tests/contract/test_acquisition.py` assert:
  - `.github/workflows/ci.yml` PR selects `["code", "delivery"]`.
  - docs-only PR selects `["code"]`.
  - `payload.affected_domains` override still wins.
- Webhook tests updated so `affected_domains` reflects the classifier output
  rather than the hardcoded triple.

## Amendment (2026-08-30): Queried-Channel Reconciliation with ADR-013

Implementing this ADR surfaced a conflict with ADR-013 (honest monitoring
unavailable state).  The cannot-assess gate (`reducer.py:202-210, 293-297`)
counts UNAVAILABLE evidence claims; those claims are emitted by the
alert/telemetry workers — which only run when `production` is selected.
If a monitoring outage caused `production` to be *deselected*, the outage
would leave no trace in the ValidatedSituation: no UNAVAILABLE claim, no
gate, and a *higher* evidence strength — the exact dishonesty ADR-013
exists to prevent.

Decision (supersedes Decision 3 for the webhook/enrichment path only):

1. In the enrichment path, every evidence channel the pipeline actually
   queries for a PR is claimed, with its honest status: changed files
   (`code`, file-derived per Decisions 1–2), CI outcome (`delivery`;
   pass/fail/unknown), and monitoring (`production`; ok/unavailable).
   See `enrichment.py:494-523`.
2. In the deterministic acquisition path (no enrichment payload), selection
   remains purely file-derived per Decisions 1–2.
3. Decision 3 stands in its essential point: the hardcoded triple with no
   query behind it is gone.  What remains is a queried-channel claim where
   every selected dimension reports observed / no_signal / unavailable.

The rejected alternative above ("force all three domains always") meant
claiming domains with nothing behind them.  The reconciliation claims only
channels that were genuinely queried and carries their status into the
evidence model, so `missing_domains` stays meaningful and a monitoring
outage can never silently *raise* confidence.