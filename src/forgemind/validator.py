"""ForgeMind Phase 5 — Tier 4 Cross-Lifecycle Validator (SPEC-001 T500).

The sole tier authorized to reconcile evidence across domain boundaries
(docs/ARCHITECTURE.md, ADR-005).  The validator accepts the ``CoveragePlan``
that selected the domains, every ``DomainFinding`` contributed by the Tier 2
managers, and (optional) raw ``EvidenceShard``\\s; verifies coverage;
reconciles supporting and conflicting evidence; deduplicates repeated
signals; distinguishes correlation from causation; and emits a single
schema-valid ``ValidatedSituation`` — the authoritative input for Tier 5
(Decision Reducer, Phase 6).  No DecisionRecord / ProposedAction is ever
produced here and no autonomous action is taken (tier restraint invariant).

Tier 4 responsibilities implemented:

1. **Evidence gathering** --- collects the findings of every selected domain.
2. **Coverage verification** --- gaps between ``selected_domains`` and the
   domains that actually contributed are recorded explicitly in the
   ``coverage`` object (``missing_domains``) and called out in a validation
   note; a coverage gap is never silently omitted (spec.md FR-005,
   Visibility of Absence).  Findings for domains the plan did NOT select
   are rejected outright (bounded-input discipline).
3. **Reconciliation** --- claims asserted verbatim in two or more domains
   become ``supporting_evidence``; cross-domain negation pairs (same
   conservative heuristic as Phase 3) become ``conflicting_evidence``.
4. **Deduplication** --- repeated signals (identical claim text or shard ids
   seen in more than one finding) are collapsed into ``deduplication``
   entries instead of being counted twice.
5. **Conservative causality** --- ``causality_status`` defaults to
   ``correlated``; ``supported`` requires a causal claim corroborated across
   domains; ``verified`` requires explicit verification language plus that
   corroboration.  Asserting causation WITHOUT cross-domain corroboration
   raises :class:`ValidatorError` --- correlation is never presented as
   causation (ADR-005).
6. **Confidence** --- weakest link wins: the aggregate confidence is the
   minimum across contributing findings (``0.0`` with no findings), and any
   sub-``0.5`` finding contributes an explicit uncertainty.
7. **Evidence-aware decisioning** --- evidence quality is modeled explicitly
   via :class:`EvidenceState` and :class:`ClaimStatus`.  Cross-worker
   consistency is checked, evidence strength is computed as a separate
   dimension from confidence, and claim provenance is verified.

Boundaries (violations are architectural bugs): the validator reconciles
across domains but NEVER decides policy, NEVER emits DecisionRecord /
ProposedAction artifacts, NEVER bypasses Tier 5, and never upgrades a
correlation into causation on its own authority.

Determinism: no wall-clock values enter the situation;
``validated_situation_id`` is a pure function of ``situation_id`` and the
number of contributing domains; identical inputs yield identical
ValidatedSituations (replay-stable).  The validator is stateless ---
:meth:`CrossLifecycleValidator.validate` returns a fresh record per call.
"""

from __future__ import annotations

from enum import Enum
from typing import Iterable, Optional

import jsonschema

from forgemind.acquisition import load_schema

__all__ = [
    "ClaimStatus",
    "CrossLifecycleValidator",
    "EvidenceState",
    "ValidatorError",
]

#: Negation prefixes — the same conservative heuristic as Phase 3
#: (``forgemind.domain_managers``).  Only a verbatim leading prefix marks a
#: claim as negated; anything else compares as its literal self.
_NEGATION_PREFIXES = ("never ", "without ", "no ", "not ", "cannot ")

#: Substrings whose presence marks a claim as making a causal assertion
#: (MVP heuristic).  ``cause`` alone covers cause/causes/caused/because.
_CAUSAL_MARKERS = ("cause", "due to", "results in", "trigger")

#: Keys that must NEVER appear on a Tier 4 artifact: emitting them would
#: mean the validator usurped Tier 5 (Reducer) authority.
_FORBIDDEN_DECISION_KEYS = (
    "decision_record_id",
    "proposed_action_id",
    "action_id",
    "action_validation_id",
    "escalation_id",
)


class EvidenceState(str, Enum):
    """Evidence quality classification for claims and observations.

    Architecture rule: **No confidence score can upgrade an evidence state.**
    ``NO_SIGNAL + confidence=0.99 ≠ OBSERVED + confidence=0.99``
    """

    OBSERVED = "observed"           # Concrete evidence found
    VERIFIED = "verified"           # Independently confirmed
    NO_SIGNAL = "no_signal"         # Worker looked, found nothing
    UNAVAILABLE = "unavailable"     # Worker could not obtain evidence
    CONTRADICTORY = "contradictory" # Conflicts with another observation


class ClaimStatus(str, Enum):
    """Provenance verification status for claims."""

    UNVERIFIED = "unverified"         # Worker claim only
    SUPPORTED = "supported"             # Corroborated by another worker
    INDEPENDENTLY_VERIFIED = "independently_verified"  # Verified against system of record


class ValidatorError(ValueError):
    """Tier 4 validation failure.

    Raised for a malformed / schema-invalid ``CoveragePlan`` or
    ``DomainFinding``, a finding covering a domain the plan did not select,
    a causation claim lacking cross-domain supporting evidence (the
    ``correlation != causation`` invariant enforced at emission time), or an
    emitted ValidatedSituation failing re-validation against its canonical
    contract.
    """


def _negation_pair(claim: str):
    """Return ``(canonical_key, positive_form)`` when ``claim`` negates.

    Mirrors Phase 3: only the first verbatim prefix is stripped; anything
    else yields ``(None, None)``.
    """
    lowered = claim.strip().lower()
    for prefix in _NEGATION_PREFIXES:
        if lowered.startswith(prefix):
            return lowered[len(prefix):], lowered[len(prefix):]
    return None, None


def _has_causal_language(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in _CAUSAL_MARKERS)


def _is_verified_causal(text: str) -> bool:
    lowered = text.lower()
    return "verif" in lowered and _has_causal_language(lowered)


def _ordered_unique(values: Iterable) -> list:
    """Order-preserving dedupe (deterministic for replay)."""
    seen = set()
    kept: list = []
    for value in values:
        if value not in seen:
            seen.add(value)
            kept.append(value)
    return kept


def _id_suffix(artifact_id: str) -> str:
    """Replay-stable suffix for generated ids (mirrors earlier tiers)."""
    for prefix in ("VS-", "SIT-", "EVT-", "CP-"):
        if artifact_id.startswith(prefix):
            return artifact_id[len(prefix):]
    return str(artifact_id or "unknown")



class CrossLifecycleValidator:
    """Stateless Tier 4 reconciler: DomainFindings -> ValidatedSituation.

    One instance may be reused for any number of validations; every
    :meth:`validate` call returns a freshly constructed record and never
    mutates its inputs.
    """

    def validate(
        self,
        coverage_plan: dict,
        domain_findings: list,
        evidence_shards: Optional[list] = None,
        repo: str = "",
        sha: str = "",
    ) -> dict:
        """Reconcile ``domain_findings`` into a single ValidatedSituation.

        Args:
            coverage_plan: the Tier 1 CoveragePlan that selected the domains
                under investigation.
            domain_findings: one DomainFinding per contributing domain, each
                schema-valid against ``contracts/domain-finding.schema.json``
                and bounded to a domain the plan selected.
            evidence_shards: optional raw EvidenceShards folded into the
                evidence index and deduplication pass.
            repo: optional repository in 'owner/repo' format for independent
                claim verification against GitHub API.
            sha: optional commit SHA for independent claim verification
                against GitHub API.

        Returns:
            A ``ValidatedSituation`` dict validating against
            ``contracts/validated-situation.schema.json``.

        Raises:
            ValidatorError: invalid plan/finding inputs, an out-of-scope
                domain, an uncorroborated causation claim, or a generated
                situation failing schema re-validation.
        """
        findings, shards = self._validate_inputs(
            coverage_plan, domain_findings, evidence_shards
        )

        selected_domains = list(coverage_plan.get("selected_domains") or [])
        provided_domains = _ordered_unique(f["domain"] for f in findings)
        missing_domains = [
            d for d in selected_domains if d not in provided_domains
        ]

        finding_ids = _ordered_unique(f["finding_id"] for f in findings)
        evidence_ids = _ordered_unique(
            [sid for f in findings for sid in f.get("evidence_shard_ids", [])]
            + [s["evidence_shard_id"] for s in shards]
        )
# __P3__

        claim_domains: dict = {}
        for finding in findings:  # input order -> deterministic output order
            domain = finding["domain"]
            for claim in finding.get("supported_claims", []):
                domains_for_claim = claim_domains.setdefault(claim, [])
                if domain not in domains_for_claim:
                    domains_for_claim.append(domain)

        supporting_evidence = [
            claim for claim, domains in claim_domains.items() if len(domains) >= 2
        ]
        conflicting_evidence = self._cross_domain_conflicts(findings)
        deduplication = self._collect_duplicates(findings, shards)
        correlations = [
            "cross-domain correlation: "
            + f"'{claim}' observed in {'+'.join(domains)}"
            for claim, domains in claim_domains.items()
            if len(domains) >= 2
        ]
        # Multi-domain presence corroboration (ADR-011): when 2+ domains
        # contribute findings, they count as corroborated even without
        # overlapping claim text (the workers ran and reported). Computed
        # BEFORE _assess_causality so multi-domain situations with causal
        # language are classified instead of raising.
        domain_count = len(set(f.get("domain") for f in findings if f.get("domain")))
        corroborated = bool(supporting_evidence) or domain_count >= 2
        causality_status = self._assess_causality(
            findings,
            corroborated=corroborated,
        )

        confidences = [float(f["confidence"]) for f in findings]
        confidence = round(sum(confidences) / len(confidences), 2) if confidences else 0.0
        weak_findings = [
            f["finding_id"]
            for f, c in zip(findings, confidences)
            if c < 0.5
        ]
        uncertainties = _ordered_unique(
            item for f in findings for item in f.get("uncertainties", [])
        )
        if weak_findings:
            uncertainties.append(
                "low-confidence finding(s) below 0.5 contributed "
                f"({', '.join(weak_findings)}); treat conclusions conservatively"
            )

        # -- evidence-aware decisioning (Fix 1, 2, 6) --------------------
        # Cross-worker consistency: detect contradictions and coverage gaps
        cross_worker_consistency = self._cross_worker_consistency(findings)
        # Evidence strength: separate dimension from confidence
        evidence_strength = self._compute_evidence_strength(findings, shards)
        # Claim provenance: verify claims against systems of record
        claim_statuses = self._verify_claim_provenance(findings, repo=repo, sha=sha)
        # Aggregate evidence states for the situation
        evidence_states = self._aggregate_evidence_states(findings, shards)

        coverage_percentage = (
            round(100.0 * len(provided_domains) / len(selected_domains))
            if selected_domains
            else 0
        )
        coverage = {
            "provided_domains": provided_domains,
            "missing_domains": missing_domains,
            "coverage_percentage": coverage_percentage,
        }

        validation_notes = [
            f"Reconciled {len(findings)} DomainFinding(s) across "
            f"{len(provided_domains)} domain(s): "
            f"{len(supporting_evidence)} supporting, "
            f"{len(conflicting_evidence)} conflicting, "
            f"{len(deduplication)} duplicate signal(s) collapsed."
        ]
        if missing_domains:
            validation_notes.append(
                f"coverage gap: no DomainFinding for selected domain(s) "
                f"{missing_domains}; flagged explicitly, never silently "
                "omitted (spec.md FR-005, Visibility of Absence)."
            )
        validation_notes.append(
            f"causality_status='{causality_status}' "
            f"({self._causality_rationale(causality_status)})."
        )
        if weak_findings:
            validation_notes.append(
                f"weakest-link confidence {confidence} driven by "
                f"{weak_findings}."
            )
        # Evidence-aware notes
        validation_notes.append(
            f"evidence_strength={evidence_strength:.2f} "
            f"({evidence_states.get('summary', 'no evidence states recorded')})"
        )
        if cross_worker_consistency.get("contradictions"):
            validation_notes.append(
                f"cross-worker contradictions detected: "
                f"{cross_worker_consistency['contradictions']}"
            )
        if cross_worker_consistency.get("coverage_gaps"):
            validation_notes.append(
                f"cross-worker coverage gaps: "
                f"{cross_worker_consistency['coverage_gaps']}"
            )

        validated = {
            "validated_situation_id": (
                f"VS-{_id_suffix(coverage_plan['situation_id'])}"
                f"-{len(provided_domains)}"
            ),
            "situation_id": coverage_plan["situation_id"],
            "finding_ids": finding_ids,
            "evidence_ids": evidence_ids,
            "supporting_evidence": supporting_evidence,
            "conflicting_evidence": conflicting_evidence,
            "coverage": coverage,
            "deduplication": deduplication,
            "correlations": correlations,
            "causality_status": causality_status,
            "confidence": confidence,
            "evidence_strength": round(evidence_strength, 2),
            "evidence_states": evidence_states,
            "claim_statuses": claim_statuses,
            "cross_worker_consistency": cross_worker_consistency,
            "uncertainties": uncertainties,
            "validation_notes": validation_notes,
            "provenance": {
                "event_id": (coverage_plan.get("provenance") or {}).get(
                    "event_id"
                ),
                "situation_id": coverage_plan["situation_id"],
                "coverage_plan_id": coverage_plan["coverage_plan_id"],
                "execution_trace_id": coverage_plan["execution_trace_id"],
                "produced_by": "CrossLifecycleValidator",
                "spec_phase": "SPEC-001-phase-5-tier-4-validator",
            },
            "execution_trace_id": coverage_plan["execution_trace_id"],
        }

        # Boundary guard: Tier 4 must never carry Tier 5 decision artifacts.
        leaked = [key for key in _FORBIDDEN_DECISION_KEYS if key in validated]
        if leaked:  # pragma: no cover - construction above cannot add these
            raise ValidatorError(
                "ValidatedSituation carries forbidden decision artifact "
                f"key(s) {leaked}; the validator never bypasses Tier 5"
            )

        try:
            jsonschema.validate(
                validated, load_schema("validated-situation.schema.json")
            )
        except jsonschema.ValidationError as exc:  # pragma: no cover
            raise ValidatorError(
                "generated ValidatedSituation failed "
                "contracts/validated-situation.schema.json: "
                f"{exc.message}"
            ) from exc
        return validated

    # -- input validation -------------------------------------------------------

    def _validate_inputs(
        self, coverage_plan: dict, domain_findings: list, evidence_shards
    ):
        """Validate the CoveragePlan and every finding/shard before use."""
        if not isinstance(coverage_plan, dict):
            raise ValidatorError("coverage_plan must be a JSON object")
        for key in ("selected_domains", "situation_id", "execution_trace_id"):
            if key not in coverage_plan:
                raise ValidatorError(f"coverage_plan missing required key {key!r}")
        if domain_findings is None:
            domain_findings = []
        if not isinstance(domain_findings, list):
            raise ValidatorError("domain_findings must be a list")

        finding_schema = load_schema("domain-finding.schema.json")
        selected = list(coverage_plan["selected_domains"])
        for index, finding in enumerate(domain_findings):
            if not isinstance(finding, dict):
                raise ValidatorError(
                    f"domain_findings[{index}] must be a JSON object"
                )
            try:
                jsonschema.validate(finding, finding_schema)
            except jsonschema.ValidationError as exc:
                raise ValidatorError(
                    f"domain_findings[{index}] failed "
                    "contracts/domain-finding.schema.json: "
                    f"{exc.message}"
                ) from exc
            if finding.get("situation_id") != coverage_plan["situation_id"]:
                raise ValidatorError(
                    f"domain_findings[{index}].situation_id "
                    f"({finding.get('situation_id')!r}) does not match "
                    f"coverage_plan.situation_id "
                    f"({coverage_plan['situation_id']!r})"
                )
            if finding.get("domain") not in selected:
                raise ValidatorError(
                    f"domain_findings[{index}] covers domain "
                    f"{finding.get('domain')!r}, which the CoveragePlan did "
                    "not select; the validator gathers ONLY selected domains"
                )

        if evidence_shards is None:
            evidence_shards = []
        if not isinstance(evidence_shards, list):
            raise ValidatorError("evidence_shards must be a list when provided")
        shard_schema = load_schema("evidence-shard.schema.json")
        for index, shard in enumerate(evidence_shards):
            if not isinstance(shard, dict):
                raise ValidatorError(
                    f"evidence_shards[{index}] must be a JSON object"
                )
            try:
                jsonschema.validate(shard, shard_schema)
            except jsonschema.ValidationError as exc:
                raise ValidatorError(
                    f"evidence_shards[{index}] failed "
                    "contracts/evidence-shard.schema.json: "
                    f"{exc.message}"
                ) from exc
        return list(domain_findings), list(evidence_shards)

    # -- reconciliation helpers --------------------------------------------------

    @staticmethod
    def _cross_domain_conflicts(findings: list) -> list:
        """Flag negation-paired claims asserted across different domains.

        Same conservative heuristic as Phase 3, applied across the domain
        boundary: a negated claim conflicts only when its positive form was
        verbatim-asserted by another contributing domain.
        """
        positives: dict = {}
        negations: dict = {}
        for finding in findings:
            domain = finding["domain"]
            for claim in finding.get("supported_claims", []):
                lowered = claim.strip().lower()
                negated_key, _positive = _negation_pair(lowered)
                if negated_key is None:
                    bucket = positives.setdefault(domain, [])
                    if lowered not in bucket:
                        bucket.append(lowered)
                else:
                    bucket = negations.setdefault(domain, [])
                    if negated_key not in bucket:
                        bucket.append(negated_key)

        conflicts: list = []
        for domain, keys in negations.items():
            for key in keys:
                for other_domain, positive_keys in positives.items():
                    if other_domain == domain:
                        continue
                    if key in positive_keys:
                        conflicts.append(
                            f"conflict: '{key}' asserted in {other_domain} "
                            f"but negated in {domain}"
                        )
                        break
        return conflicts

    @staticmethod
    def _collect_duplicates(findings: list, shards: list) -> list:
        """Collapse signals repeated across findings into dedup entries."""
        deduplication: list = []
        seen_claims: dict = {}
        seen_shards: dict = {}
        for finding in findings:
            domain = finding["domain"]
            for shard_id in finding.get("evidence_shard_ids", []):
                first_domain = seen_shards.setdefault(shard_id, domain)
                if first_domain != domain:
                    deduplication.append(
                        f"{shard_id} collapsed (repeated shard id; first "
                        f"contributed by {first_domain})"
                    )
            for claim in finding.get("supported_claims", []):
                first_domain = seen_claims.setdefault(claim, domain)
                if first_domain != domain:
                    deduplication.append(
                        f"duplicate signal '{claim}' collapsed "
                        f"({first_domain} + {domain})"
                    )
        for shard in shards:
            shard_id = shard["evidence_shard_id"]
            first_domain = seen_shards.setdefault(shard_id, shard.get("domain"))
            if first_domain != shard.get("domain"):
                deduplication.append(
                    f"{shard_id} collapsed (raw shard repeats an already "
                    "indexed signal)"
                )
        return _ordered_unique(deduplication)

    # -- conservative causality ---------------------------------------------------

    @staticmethod
    def _assess_causality(findings: list, *, corroborated: bool) -> str:
        """Classify the situation; reject uncorroborated causation claims.

        MVP heuristic (Phase 6 may strengthen it):

        - ``verified``  — a claim explicitly marked as verified asserts
          causation AND cross-domain corroboration exists.
        - ``supported`` — a causal claim exists AND cross-domain
          corroboration exists.
        - ``correlated`` — no causal language, but cross-domain signals
          correlate (the conservative default).
        - ``unsupported`` — neither causal language nor correlation.

        Any causal assertion WITHOUT corroboration raises
        :class:`ValidatorError`: the validator refuses to relay a causation
        claim the evidence does not back (correlation != causation).
        """
        saw_verified = False
        saw_causal = False
        for finding in findings:
            for claim in finding.get("supported_claims", []):
                if _is_verified_causal(claim):
                    saw_verified = True
                elif _has_causal_language(claim):
                    saw_causal = True

        if saw_verified:
            if not corroborated:
                raise ValidatorError(
                    "verified-causation claim without cross-domain "
                    "supporting evidence; correlation is never presented "
                    "as verified causation (ADR-005)"
                )
            return "verified"
        if saw_causal:
            if not corroborated:
                raise ValidatorError(
                    "causation claimed without cross-domain supporting "
                    "evidence; the validator emits correlation, never "
                    "unsupported causation (ADR-005)"
                )
            return "supported"
        if corroborated:
            return "correlated"
        return "unsupported"

    @staticmethod
    def _causality_rationale(status: str) -> str:
        """Human-readable rationale recorded beside ``causality_status``."""
        return {
            "verified": (
                "explicitly verified causal claim corroborated across domains"
            ),
            "supported": "causal claim corroborated across domains",
            "correlated": (
                "cross-domain correlation only; causation not established"
            ),
            "unsupported": "no cross-domain signal to assess causation",
        }.get(status, "heuristic")

    # -- evidence-aware decisioning (Fix 1, 2, 6) -------------------------------

    @staticmethod
    def _extract_structured_claims(findings: list, shards: list) -> list:
        """Extract structured claims with evidence state from findings and shards.

        Each claim is a dict with: claim, value, evidence, source, evidence_state.
        Claims from findings use the finding's domain and claims list.
        Claims from shards use the shard's structured claims if present.
        """
        structured = []
        for finding in findings:
            domain = finding.get("domain", "unknown")
            for claim_text in finding.get("supported_claims", []):
                # Determine evidence state: if the claim has evidence, it's OBSERVED
                evidence_state = EvidenceState.OBSERVED.value
                # Check if this is a "no signal" type claim
                lowered = claim_text.lower()
                if any(
                    phrase in lowered
                    for phrase in (
                        "no ",
                        "no signal",
                        "nothing found",
                        "no evidence",
                        "no claim",
                        "no dependency",
                        "no doc",
                        "no alert",
                        "no telemetry",
                        "no changed",
                        "no build",
                    )
                ):
                    evidence_state = EvidenceState.NO_SIGNAL.value
                structured.append(
                    {
                        "claim": claim_text,
                        "value": True,
                        "evidence": [finding.get("finding_id", "unknown")],
                        "source": f"domain_finding:{domain}",
                        "evidence_state": evidence_state,
                        "domain": domain,
                    }
                )
        for shard in shards:
            domain = shard.get("domain", "unknown")
            worker = shard.get("worker", "unknown")
            # Use structured claims from shard if present
            for claim in shard.get("claims", []):
                if isinstance(claim, dict):
                    structured.append(
                        {
                            "claim": claim.get("claim", ""),
                            "value": claim.get("value", True),
                            "evidence": claim.get("evidence", []),
                            "source": claim.get("source", f"shard:{worker}"),
                            "evidence_state": claim.get(
                                "evidence_state", EvidenceState.OBSERVED.value
                            ),
                            "domain": domain,
                        }
                    )
                else:
                    # String claim from shard
                    evidence_state = EvidenceState.OBSERVED.value
                    lowered = str(claim).lower()
                    if any(
                        phrase in lowered
                        for phrase in (
                            "no ",
                            "no signal",
                            "nothing found",
                            "no evidence",
                            "no claim",
                            "no dependency",
                            "no doc",
                            "no alert",
                            "no telemetry",
                            "no changed",
                            "no build",
                        )
                    ):
                        evidence_state = EvidenceState.NO_SIGNAL.value
                    structured.append(
                        {
                            "claim": str(claim),
                            "value": True,
                            "evidence": [shard.get("evidence_shard_id", "unknown")],
                            "source": f"shard:{worker}",
                            "evidence_state": evidence_state,
                            "domain": domain,
                        }
                    )
        return structured

    def _cross_worker_consistency(self, findings: list) -> dict:
        """Check cross-worker consistency (Fix 1).

        Detects:
        - Contradictions: two workers with conflicting claims
        - Coverage gaps: expected evidence missing (e.g., CI unknown but PR
          touches .github/workflows/*)

        Returns dict with ``contradictions`` and ``coverage_gaps`` lists.
        """
        contradictions = []
        coverage_gaps = []

        # Build claim index: claim_text -> list of (domain, finding_id)
        claim_index: dict = {}
        for finding in findings:
            domain = finding.get("domain", "unknown")
            for claim_text in finding.get("supported_claims", []):
                claim_index.setdefault(claim_text, []).append(
                    (domain, finding.get("finding_id", "unknown"))
                )

        # Check for negation-based contradictions across domains
        all_positives = {}
        all_negations = {}
        for finding in findings:
            domain = finding.get("domain", "unknown")
            for claim_text in finding.get("supported_claims", []):
                lowered = claim_text.strip().lower()
                negated_key, _ = _negation_pair(lowered)
                if negated_key is None:
                    all_positives.setdefault(domain, []).append(lowered)
                else:
                    all_negations.setdefault(domain, []).append(negated_key)

        for neg_domain, neg_keys in all_negations.items():
            for neg_key in neg_keys:
                for pos_domain, pos_keys in all_positives.items():
                    if pos_domain == neg_domain:
                        continue
                    if neg_key in pos_keys:
                        contradictions.append(
                            f"'{neg_key}' asserted in {pos_domain} "
                            f"but negated in {neg_domain}"
                        )

        # Check for evidence gaps: if code domain has dependency changes
        # but security domain has no scan results
        code_claims = []
        security_claims = []
        for finding in findings:
            domain = finding.get("domain")
            if domain == "code":
                code_claims.extend(finding.get("supported_claims", []))
            elif domain == "production":
                security_claims.extend(finding.get("supported_claims", []))

        # If code worker reports dependency file changes, security should have
        # run a dependency scan
        code_text = " ".join(code_claims).lower()
        security_text = " ".join(security_claims).lower()
        if (
            "package.json" in code_text
            or "dependency" in code_text
            or "requirements.txt" in code_text
        ):
            if "scan" not in security_text and "dependency" not in security_text:
                coverage_gaps.append(
                    "code domain reports dependency changes but production "
                    "domain has no dependency scan evidence"
                )

        # If PR touches .github/workflows/*, build worker should have CI data
        if ".github/workflows" in code_text:
            delivery_claims = []
            for finding in findings:
                if finding.get("domain") == "delivery":
                    delivery_claims.extend(finding.get("supported_claims", []))
            delivery_text = " ".join(delivery_claims).lower()
            if "ci" not in delivery_text and "build" not in delivery_text:
                coverage_gaps.append(
                    "code domain reports workflow changes but delivery "
                    "domain has no CI/build evidence"
                )

        return {
            "contradictions": contradictions,
            "coverage_gaps": coverage_gaps,
            "is_consistent": not contradictions and not coverage_gaps,
        }

    @staticmethod
    def _compute_evidence_strength(findings: list, shards: list) -> float:
        """Compute evidence strength as a separate dimension from confidence.

        Evidence strength = count(workers with OBSERVED or VERIFIED evidence) / total workers

        Architecture rule: NO_SIGNAL cannot satisfy positive-evidence requirement.
        UNAVAILABLE cannot count as corroboration.
        """
        if not findings and not shards:
            return 0.0

        # Count total unique workers/domains that contributed
        total_workers = set()
        observed_workers = set()

        for finding in findings:
            domain = finding.get("domain", "unknown")
            total_workers.add(domain)
            # Check if finding has actual evidence (not just "no signal" claims)
            claims = finding.get("supported_claims", [])
            has_observed = False
            for claim in claims:
                lowered = claim.lower()
                # A claim is NO_SIGNAL if it starts with negation or contains
                # explicit "no signal" language
                is_no_signal = any(
                    phrase in lowered
                    for phrase in (
                        "no signal",
                        "nothing found",
                        "no evidence",
                        "no claim",
                        "no dependency",
                        "no doc",
                        "no alert",
                        "no telemetry",
                        "no changed",
                        "no build",
                        "no dependency security claim",
                        "no doc drift claim",
                        "no alert storm cluster claim",
                        "no telemetry correlation claim",
                        "no build claim supported",
                        "changeset contains no;",
                    )
                )
                if not is_no_signal:
                    has_observed = True
            if has_observed:
                observed_workers.add(domain)

        for shard in shards:
            worker = shard.get("worker", "unknown")
            total_workers.add(worker)
            # Check structured claims in shard
            claims = shard.get("claims", [])
            has_observed = False
            for claim in claims:
                if isinstance(claim, dict):
                    if claim.get("evidence_state") in (
                        EvidenceState.OBSERVED.value,
                        EvidenceState.VERIFIED.value,
                    ):
                        has_observed = True
                else:
                    lowered = str(claim).lower()
                    is_no_signal = any(
                        phrase in lowered
                        for phrase in (
                            "no signal",
                            "nothing found",
                            "no evidence",
                            "no claim",
                            "no dependency",
                            "no doc",
                            "no alert",
                            "no telemetry",
                            "no changed",
                            "no build",
                        )
                    )
                    if not is_no_signal:
                        has_observed = True
            if has_observed:
                observed_workers.add(worker)

        if not total_workers:
            return 0.0
        return len(observed_workers) / len(total_workers)

    @staticmethod
    def _verify_claim_provenance(
        findings: list, repo: str = "", sha: str = ""
    ) -> dict:
        """Verify claim provenance, including independent verification.

        For each claim:
        1. Check if a verifier exists (via VerifierRegistry)
        2. If yes and repo/sha provided → query external source
        3. If confirmed → INDEPENDENTLY_VERIFIED
        4. If not confirmed or no verifier → check cross-domain matching
        5. If corroborated by another domain → SUPPORTED
        6. Otherwise → UNVERIFIED

        Architecture rule: **If no verifier exists for a claim type, the
        claim stays UNVERIFIED. Inference alone cannot upgrade to
        INDEPENDENTLY_VERIFIED.**

        Args:
            findings: List of DomainFinding dicts with supported_claims.
            repo: Optional repository in 'owner/repo' format. When empty,
              falls back to local-only cross-domain matching.
            sha: Optional commit SHA. When empty, falls back to local-only
              cross-domain matching.

        Returns:
            Dict mapping claim text to its ClaimStatus value string.
        """
        # Import here to avoid circular import at module load
        from forgemind.verification import VerifierRegistry

        claim_statuses = {}

        # Build claim -> domains index
        claim_domains: dict = {}
        for finding in findings:
            domain = finding.get("domain", "unknown")
            for claim_text in finding.get("supported_claims", []):
                domains = claim_domains.setdefault(claim_text, [])
                if domain not in domains:
                    domains.append(domain)

        for claim_text, domains in claim_domains.items():
            # Step 1: Try independent verification if repo/sha available
            if repo and sha:
                structured_claim = {"claim": claim_text}
                verified_status = VerifierRegistry.verify(
                    structured_claim, repo, sha
                )
                if verified_status == ClaimStatus.INDEPENDENTLY_VERIFIED:
                    claim_statuses[claim_text] = (
                        ClaimStatus.INDEPENDENTLY_VERIFIED.value
                    )
                    continue

            # Step 2: Fall back to cross-domain corroboration
            if len(domains) >= 2:
                claim_statuses[claim_text] = ClaimStatus.SUPPORTED.value
            else:
                claim_statuses[claim_text] = ClaimStatus.UNVERIFIED.value

        return claim_statuses

    @staticmethod
    def _aggregate_evidence_states(findings: list, shards: list) -> dict:
        """Aggregate evidence states across all findings and shards.

        Returns a summary dict with counts and dominant state.
        """
        states = {
            EvidenceState.OBSERVED.value: 0,
            EvidenceState.VERIFIED.value: 0,
            EvidenceState.NO_SIGNAL.value: 0,
            EvidenceState.UNAVAILABLE.value: 0,
            EvidenceState.CONTRADICTORY.value: 0,
        }

        for finding in findings:
            for claim in finding.get("supported_claims", []):
                lowered = str(claim).lower()
                if "unavailable" in lowered:
                    # Honest fail-closed (ADR-013): a claim that records an
                    # unassessable source is UNAVAILABLE, never NO_SIGNAL.
                    # Checked first: "monitoring source unavailable; no alert
                    # assessment possible" also contains no_signal phrases.
                    states[EvidenceState.UNAVAILABLE.value] += 1
                elif any(
                    phrase in lowered
                    for phrase in (
                        "no signal",
                        "nothing found",
                        "no evidence",
                        "no claim",
                        "no dependency",
                        "no doc",
                        "no alert",
                        "no telemetry",
                        "no changed",
                        "no build",
                        "no dependency security claim",
                        "no doc drift claim",
                        "no alert storm cluster claim",
                        "no telemetry correlation claim",
                        "no build claim supported",
                        "changeset contains no;",
                    )
                ):
                    states[EvidenceState.NO_SIGNAL.value] += 1
                else:
                    states[EvidenceState.OBSERVED.value] += 1

        for shard in shards:
            structured = shard.get("structured_claims") or []
            if structured:
                # Authoritative typed channel: ``evidence_state`` travels on
                # each structured claim (workers.py ``_build_structured_claims``,
                # including the ADR-013 UNAVAILABLE override).  Counted instead
                # of the parallel string claims to avoid double counting.
                for claim in structured:
                    if isinstance(claim, dict):
                        state = claim.get(
                            "evidence_state", EvidenceState.OBSERVED.value
                        )
                        if state in states:
                            states[state] += 1
                    else:  # defensive: tolerate malformed entries
                        lowered = str(claim).lower()
                        if "unavailable" in lowered:
                            states[EvidenceState.UNAVAILABLE.value] += 1
                        elif any(
                            phrase in lowered
                            for phrase in (
                                "no signal",
                                "nothing found",
                                "no evidence",
                                "no claim",
                            )
                        ):
                            states[EvidenceState.NO_SIGNAL.value] += 1
                        else:
                            states[EvidenceState.OBSERVED.value] += 1
            else:
                # String-only shards (legacy/manager-level): phrase heuristic.
                for claim in shard.get("claims", []):
                    if isinstance(claim, dict):
                        state = claim.get(
                            "evidence_state", EvidenceState.OBSERVED.value
                        )
                        if state in states:
                            states[state] += 1
                    else:
                        lowered = str(claim).lower()
                        if "unavailable" in lowered:
                            states[EvidenceState.UNAVAILABLE.value] += 1
                        elif any(
                            phrase in lowered
                            for phrase in (
                                "no signal",
                                "nothing found",
                                "no evidence",
                                "no claim",
                            )
                        ):
                            states[EvidenceState.NO_SIGNAL.value] += 1
                        else:
                            states[EvidenceState.OBSERVED.value] += 1

        total = sum(states.values())
        dominant = (
            max(states, key=lambda k: states[k]) if total > 0 else "none"
        )
        summary = (
            f"{states[EvidenceState.OBSERVED.value]} observed, "
            f"{states[EvidenceState.NO_SIGNAL.value]} no_signal, "
            f"{states[EvidenceState.VERIFIED.value]} verified, "
            f"{states[EvidenceState.UNAVAILABLE.value]} unavailable, "
            f"{states[EvidenceState.CONTRADICTORY.value]} contradictory"
        )

        return {
            "counts": states,
            "total": total,
            "dominant_state": dominant,
            "summary": summary,
        }