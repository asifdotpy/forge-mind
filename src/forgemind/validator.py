"""ForgeMind Phase 5 — Tier 4 Cross-Lifecycle Validator (SPEC-001 T500).

The sole tier authorized to reconcile evidence across domain boundaries
(docs/ARCHITECTURE.md, ADR-005).  The validator accepts the ``CoveragePlan``
that selected the domains, every ``DomainFinding`` contributed by the Tier 2
managers, and (optionally) raw ``EvidenceShard``\\s; verifies coverage;
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

from typing import Iterable, Optional

import jsonschema

from forgemind.acquisition import load_schema

__all__ = ["CrossLifecycleValidator", "ValidatorError"]

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
        causality_status = self._assess_causality(
            findings,
            corroborated=bool(supporting_evidence),
        )

        confidences = [float(f["confidence"]) for f in findings]
        confidence = min(confidences) if confidences else 0.0
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