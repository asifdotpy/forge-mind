# ForgeMind — Project Story (Devpost submission)

> Format target: Devpost "About the project" field (Markdown, LaTeX-supported).
> Copy from `## Inspiration` to the end. Every claim is verified against the
> repo, the live Cloud Run service, the test run, and real GitHub PRs.

## Inspiration

Engineering teams live in disconnected signals. A PR opens, a build goes red, an alert fires at 2 a.m. — and nobody connects the dots until something breaks in production. Each signal lives in a different tool, a different dashboard, a different tired on-call engineer. We wanted to build the system we wished existed: one that treats a PR, a build failure, and a production alert as *the same kind of event* — an engineering situation that deserves planning, evidence, validation, and a deliberate decision about whether a machine or a human should act.

The **Fortified Enterprise Fleet** track gave us the mandate: enterprise agents shouldn't just be clever, they should be **governed** — with scoped authority, provable evidence, and a hard boundary that keeps a human in control. That became ForgeMind's north star: *more autonomy where evidence supports it, honest escalation where it doesn't.*

## What it does

ForgeMind is an autonomous engineering control plane built on a **five-tier hierarchical multi-agent DAG**:

```
Supervisor → Domain Managers → Specialist Workers → Cross-Lifecycle Validator → Decision Reducer
```

Feed the system a real event — a GitHub PR, a CI failure, a production alert — and it:

1. **Plans** — the Engineering Supervisor derives a CoveragePlan across code, delivery, and production health.
2. **Investigates** — six specialist workers emit durable, schema-validated EvidenceShards with source citations.
3. **Reconciles** — three domain managers aggregate shards into DomainFindings, and the Cross-Lifecycle Validator reconciles them into a ValidatedSituation with explicit coverage and causality assessments.
4. **Decides — and only then.** The Decision Reducer is the *sole* decision authority. A deterministic autonomy ladder automates low-risk, well-evidenced outcomes and escalates everything uncertain or high-blast-radius to a human — with the full evidence chain attached.

Every artifact carries upstream provenance (`Event → CoveragePlan → EvidenceShard → DomainFinding → ValidatedSituation → DecisionRecord → ProposedAction → ActionValidation → Action | Escalation`), and a no-bypass ActionValidation gate is the only publish point. The judge-visible surface exposes the four properties that matter: **provenance, validation, uncertainty, human control.**

ForgeMind is live. It runs on Google Cloud Run and — on the day we're submitting — analyzed two real pull requests on a public repo and posted genuine analysis comments to GitHub. Both were escalated to a human rather than auto-approved, because the evidence did not justify autonomous action. Escalating when uncertain is the feature, not a bug.

## How we built it

- **Real Gemini 3.5 via Vertex AI** (`google-genai`), deliberately **bounded to a single worker node**: it generates evidence narrative and claims, never decisions, and fails closed to deterministic logic on any error.
- **Google ADK 2** (`google-adk`) as the workflow runtime — `adk_runtime.py` wires the DAG as an explicit, pause/resume-capable workflow with a human-approval gate, and a full ADK 2.0 Runner path drives the stages through tool functions.
- **Google Cloud Run** (`forgemind-v3-prod`, us-central1) — serverless, scale-to-zero, with a reproducible `deploy/deploy.sh` → Cloud Build → Artifact Registry → Cloud Run pipeline and a health-checked container.
- **Contract-first, spec-driven development**: 9 canonical JSON Schema contracts, 14 Architecture Decision Records, 7 fixture groups, and a fixture runner that validates the whole `Event → Terminal` lineage end-to-end.
- **Engineering honesty as tooling**: a failure log that records real incidents (a leaked token we caught and regression-gated, a dead safety gate we found by black-box testing) and the tests that prevent each from returning.

## Challenges we ran into

- **Keeping confidence honest.** Early confidence was inflated by ungrounded reasoning. We rebuilt decisioning around evidence-aware calibration (ADR-011): the calibrated model is

$$c = 0.85 + 0.15 \cdot s$$

where $s$ is the fraction of workers with *observed* (not assumed) evidence. The same real PR dropped from 0.79 to 0.23 after calibration — humbling, and correct.
- **A safety gate that was dead code.** Black-box probing showed our "cannot assess ⇒ require human" monitoring gate never fired on the live path — evidence traveled on two channels and one was never read (FAIL-006). We fixed the aggregation and added a full-pipeline contract test.
- **Cloud Run's read-only filesystem.** The situation store needed an in-memory fallback so the live service survives scale-to-zero and container replacement.
- **Scope discipline.** The hardest part of the "Fortified" track was resisting LLM-everywhere. We chose bounded, deterministic, testable tiers instead — and kept the suite green as the safety net that makes that choice safe.

## Accomplishments that we're proud of

- **A real, deployed system — not a mockup.** Live on Cloud Run, 6 ADK agents registered, real Gemini-backed enrichment, real comments posted to real GitHub PRs.
- **298 tests green (1 skipped, live-token-gated)** across contracts, tier invariants, ADK runtime, secret handling, and adversarial evaluation.
- **Provenance as a product feature** — every artifact end-to-end traceable, demonstrated on the judge surface.
- **An honest autonomous posture.** Across 28 real PRs evaluated, ForgeMind approved zero actions it couldn't support and escalated the rest — conservative-by-design behavior the enterprise track rewards.
- **Adversarial self-review.** A failure log that records what went wrong and how it was fixed — transparency judges can actually read.

## What we learned

1. **Bounded LLM scope beats LLM-everywhere.** Confining Gemini to one worker node kept the deterministic suite green and preserved architectural invariants.
2. **Provenance is the trust mechanism, not overhead.** Carrying trace and upstream refs through every artifact made "human control" trivially demonstrable.
3. **Fail-closed AI is demo-safe.** Any model error degrades to deterministic output, so the system stays runnable even when the model is unavailable.
4. **Honesty applies to what was attempted, not what succeeded.** An unreachable monitoring channel must still claim its domain and report `UNAVAILABLE` — never silently raise confidence.

## What's next for ForgeMind

- **Resolve the acknowledged design debt** — move from a linear execution pipeline to true hierarchical multi-agent coordination.
- **Durable cross-session memory** — promote the dev-time Knowledge Brain to a runtime Memory Bank (ADR-009 keeps it dev-only today).
- **Managed hardening** — Google Cloud Model Armor and OTel-based distributed tracing.
- **Slack integration + daily standup** (already planned) so humans review and are briefed in the tools they already use.