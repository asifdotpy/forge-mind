"""ForgeMind Phase 1 — Contracts & Event Acquisition (SPEC-001 T100).

Implements the *Acquire* stage of the canonical runtime lifecycle::

    Acquire -> Analyze -> Reconcile -> Produce -> Validate

as the deterministic lineage prefix required by plan.md Phase 1::

    Event -> CoveragePlan

Pipeline performed by :func:`acquire_event`:

1. **Normalize** — canonicalize ``source`` (trim/lowercase) and
   ``timestamp`` (ISO-8601 parsed, converted to UTC, rendered ``...Z``),
   mirroring the Acquire Layer order *Normalize · Validate*
   (docs/ARCHITECTURE.md).  Provenance is preserved verbatim.
2. **Validate** — the normalized event must conform to
   ``contracts/event.schema.json``.  ``jsonschema`` does not enforce
   ``format: date-time`` unless a format-checker backend is installed,
   so acquisition additionally enforces timestamp parseability
   explicitly during normalization.
3. **Derive IDs** — ``execution_trace_id`` and ``coverage_plan_id`` are
   pure functions of ``event_id`` (``TRC-<suffix>`` / ``CP-<suffix>``);
   ``situation_id`` is accepted from the event.  Identifiers are stable
   across replays (idempotency).
4. **Emit CoveragePlan** — deterministic domain selection
   (``payload.affected_domains`` override, else event-type default map),
   Tier 2 manager and Tier 3 worker mapping per docs/ARCHITECTURE.md,
   excluded workers retained for visibility of absence.
5. **Re-validate** — the emitted CoveragePlan must conform to
   ``contracts/coverage-plan.schema.json``.

Determinism contract: no wall-clock values enter any returned artifact,
so identical inputs produce byte-identical artifacts.

Phase 2 (SPEC-001 T200 — Tier 1 Supervisor): ``coverage_requirements``
and ``global_constraints`` are populated with canonical defaults so the
:class:`forgemind.supervisor.Supervisor` can enforce them at dispatch.

Out of scope (later phases): EvidenceShard, DomainFinding,
ValidatedSituation, DecisionRecord, ProposedAction, ActionValidation,
Escalation; execution of dispatched managers (Tier 2, Phase 3).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import jsonschema

from forgemind._paths import CONTRACTS_DIR

__all__ = [
    "EventValidationError",
    "MANAGERS_BY_DOMAIN",
    "acquire_event",
    "load_schema",
    "normalize_event",
    "persist_artifacts",
]


class EventValidationError(ValueError):
    """An inbound event failed schema conformance or normalization."""


# ---------------------------------------------------------------------------
# Deterministic domain partitioning (docs/ARCHITECTURE.md Tier 2/3 names)
# ---------------------------------------------------------------------------

#: Canonical domain order — derived arrays are always emitted in this order.
_CANONICAL_DOMAINS = ("code", "delivery", "production")

#: Default domain selection per canonical event type (Phase 1 baseline).
_DOMAINS_BY_EVENT_TYPE = {
    "pr": ("code",),
    "documentation": ("code",),
    "ci_failure": ("delivery",),
    "deployment": ("delivery",),
    "notification": ("delivery",),
    "incident": ("production",),
    "security": ("production",),
}

_MANAGERS_BY_DOMAIN = {
    "code": "code-intelligence-manager",
    "delivery": "delivery-health-manager",
    "production": "production-health-manager",
}

#: Public alias for downstream tiers — e.g. the Phase 2 Supervisor reads
#: the canonical domain -> manager ownership map for dispatch validation.
MANAGERS_BY_DOMAIN = _MANAGERS_BY_DOMAIN

_WORKERS_BY_DOMAIN = {
    "code": ("pr-pre-flight-ast-worker", "docs-drift-and-spec-worker"),
    "delivery": (
        "build-log-and-flakiness-worker",
        "alert-storm-clustering-worker",
    ),
    "production": (
        "telemetry-correlation-worker",
        "security-and-dependency-worker",
    ),
}

_ALL_WORKERS = tuple(
    worker for domain in _CANONICAL_DOMAINS for worker in _WORKERS_BY_DOMAIN[domain]
)


# ---------------------------------------------------------------------------
# File-to-domain classification (ADR-014)
# ---------------------------------------------------------------------------
# A PR event's coverage domains are derived from the changed file paths.  This
# is deterministic and replay-stable (no wall clock, no randomness).  The
# ``code`` domain is always selected for a PR (the repository content changed);
# ``delivery`` / ``production`` are added when the changeset touches paths that
# clearly concern the delivery pipeline or security-sensitive boundaries.
# Every non-matching path falls into the default ``code`` bucket.

#: Path prefixes that clearly concern the delivery pipeline (CI/CD, deploy).
_DELIVERY_PATH_PREFIXES = (
    ".github/workflows/",
    ".github/actions/",
    ".circleci/",
    ".buildkite/",
    "buildkite/",
    "deploy/",
    "deployment/",
    "docker/",
    "infra/",
)
#: Exact filenames (case-insensitive) that concern the delivery pipeline.
_DELIVERY_FILE_NAMES = (
    "jenkinsfile",
    ".travis.yml",
    ".gitlab-ci.yml",
    "azure-pipelines.yml",
    "bitbucket-pipelines.yml",
    "dockerfile",
    "cloudbuild.yaml",
)

#: Path prefixes at the security-sensitive boundary (production concerns).
_PRODUCTION_PATH_PREFIXES = (
    "auth/",
    "security/",
    "secrets/",
    ".ssh/",
)
#: Sensitive file extensions.
_PRODUCTION_FILE_SUFFIXES = (
    ".pem",
    ".key",
    ".p12",
    ".jks",
)


def _is_delivery_path(filename: str) -> bool:
    """True when ``filename`` clearly concerns the delivery pipeline."""
    lower = filename.lower()
    if any(lower.startswith(p) for p in _DELIVERY_PATH_PREFIXES):
        return True
    return lower in _DELIVERY_FILE_NAMES


def _is_production_path(filename: str) -> bool:
    """True when ``filename`` lives at a security-sensitive boundary."""
    lower = filename.lower()
    if any(lower.startswith(p) for p in _PRODUCTION_PATH_PREFIXES):
        return True
    if any(lower.endswith(s) for s in _PRODUCTION_FILE_SUFFIXES):
        return True
    return False


def classify_changed_files_domains(changed_files) -> list:
    """Derive the canonical ordered coverage domains for a PR changeset.

    Args:
        changed_files: iterable of changed filenames (strings).

    Returns:
        ``["code"]`` always, plus ``delivery`` / ``production`` when the
        changeset touches matching paths.  Order follows
        :data:`_CANONICAL_DOMAINS` (deterministic).
    """
    domains = {"code"}
    for filename in changed_files or []:
        if _is_delivery_path(filename):
            domains.add("delivery")
        if _is_production_path(filename):
            domains.add("production")
    return [d for d in _CANONICAL_DOMAINS if d in domains]

#: Canonical downstream chain after CoveragePlan (data-model.md §1).
_DOWNSTREAM_ARTIFACTS = (
    "EvidenceShard",
    "DomainFinding",
    "ValidatedSituation",
    "DecisionRecord",
    "ProposedAction",
    "ActionValidation",
)

_SCHEMA_CACHE = {}


def load_schema(name: str) -> dict:
    """Load a canonical JSON Schema contract from ``contracts/`` (cached)."""
    if name not in _SCHEMA_CACHE:
        with (CONTRACTS_DIR / name).open(encoding="utf-8") as handle:
            _SCHEMA_CACHE[name] = json.load(handle)
    return _SCHEMA_CACHE[name]


def normalize_timestamp(value: str) -> str:
    """Return ``value`` as canonical UTC ISO-8601 (``YYYY-MM-DDTHH:MM:SSZ``).

    Raises :class:`EventValidationError` for values that are not valid
    ISO-8601 or that lack timezone information.
    """
    try:
        parsed = datetime.fromisoformat(str(value).strip())
    except ValueError as exc:
        raise EventValidationError(
            f"timestamp is not valid ISO-8601: {value!r}"
        ) from exc
    if parsed.tzinfo is None:
        raise EventValidationError(
            f"timestamp is missing timezone information: {value!r}"
        )
    normalized = parsed.astimezone(timezone.utc).isoformat()
    return normalized.replace("+00:00", "Z")


def normalize_event(event: dict) -> dict:
    """Return a deterministically normalized shallow copy of ``event``.

    Only fields with a well-defined canonical form are rewritten
    (``source``, ``timestamp``); everything else — notably
    ``provenance`` — is preserved verbatim.
    """
    normalized = dict(event)
    source = normalized.get("source")
    if isinstance(source, str):
        normalized["source"] = source.strip().lower()
    timestamp = normalized.get("timestamp")
    if isinstance(timestamp, str):
        normalized["timestamp"] = normalize_timestamp(timestamp)
    return normalized


def _id_suffix(event_id: str) -> str:
    """Strip the canonical ``EVT-`` prefix; the schema guarantees it."""
    return event_id[len("EVT-"):] if event_id.startswith("EVT-") else event_id


def derive_execution_trace_id(event_id: str) -> str:
    """Root trace id — pure function of ``event_id`` (replay-stable)."""
    return f"TRC-{_id_suffix(event_id)}"


def derive_coverage_plan_id(event_id: str) -> str:
    """CoveragePlan id — pure function of ``event_id`` (replay-stable)."""
    return f"CP-{_id_suffix(event_id)}"


def _select_domains(event: dict):
    """Return ``(selected_domains, rationale_lines)`` deterministically."""
    payload = event.get("payload") or {}
    declared = payload.get("affected_domains")
    if isinstance(declared, list) and declared:
        selected = [d for d in _CANONICAL_DOMAINS if d in declared]
        if selected:
            return selected, [
                "selected_domains taken from payload.affected_domains "
                "(filtered to canonical domains)",
            ]
    # PR events: derive coverage from the changed files (ADR-014).  A PR that
    # touches CI/CD config selects delivery, security-sensitive paths select
    # production, and everything else stays in the default code domain.
    changed_files = payload.get("changed_files")
    if event.get("type") == "pr" and isinstance(changed_files, list):
        selected = classify_changed_files_domains(changed_files)
        return selected, [
            "selected_domains derived from changed_files "
            f"({len(changed_files)} file(s)) via "
            "classify_changed_files_domains (ADR-014)",
        ]
    selected = [
        d
        for d in _CANONICAL_DOMAINS
        if d in _DOMAINS_BY_EVENT_TYPE.get(event.get("type", ""), ())
    ]
    return selected, [
        "selected_domains defaulted from the event-type map "
        "(payload.affected_domains absent or unusable)",
    ]


def _build_coverage_plan(event: dict, execution_trace_id: str) -> dict:
    """Build the deterministic Phase 1 CoveragePlan for ``event``."""
    domains, domain_rationale = _select_domains(event)
    managers = [_MANAGERS_BY_DOMAIN[d] for d in domains]
    workers = [w for d in domains for w in _WORKERS_BY_DOMAIN[d]]
    excluded = [w for w in _ALL_WORKERS if w not in workers]
    return {
        "coverage_plan_id": derive_coverage_plan_id(event["event_id"]),
        "situation_id": event["situation_id"],
        "selected_domains": domains,
        "selected_managers": managers,
        "selected_workers": workers,
        "selection_rationale": [
            *domain_rationale,
            "managers/workers mapped per docs/ARCHITECTURE.md "
            "Tier 2/Tier 3 ownership",
            "excluded_workers retained for visibility of absence "
            "(constitution invariant)",
            "coverage_requirements/global_constraints populated with "
            "Phase 2 defaults (enforced by the Tier 1 Supervisor)",
        ],
        "excluded_workers": excluded,
        "coverage_requirements": {
            "min_domains": 1,
            "max_domains": 3,
        },
        "global_constraints": {
            "max_concurrent_managers": 3,
            "global_timeout_seconds": 300,
            "require_human_above_risk_level": "critical",
        },
        "expected_artifacts": list(_DOWNSTREAM_ARTIFACTS),
        "provenance": {
            "event_id": event["event_id"],
            "produced_by": "forgemind.acquisition.acquire_event",
            "spec_phase": "SPEC-001-phase-1-contracts-event-acquisition",
        },
        "execution_trace_id": execution_trace_id,
    }


def acquire_event(event, *, execution_trace_id=None):
    """Acquire one inbound engineering Event (Phase 1, SPEC-001 T100).

    Normalize -> validate against ``contracts/event.schema.json`` ->
    derive replay-stable identifiers -> emit a deterministic
    ``CoveragePlan`` -> re-validate it against
    ``contracts/coverage-plan.schema.json``.

    Args:
        event: inbound event dict (canonical Event envelope).
        execution_trace_id: optional explicit trace id; must match
            ``^TRC-[A-Za-z0-9-]+$``.  Derived from ``event_id`` when
            omitted.

    Returns:
        dict with keys ``event`` (normalized), ``coverage_plan``
        (deterministic) and ``execution_trace_id``.

    Raises:
        EventValidationError: schema or normalization failure.

    Deterministic and side-effect free: no wall-clock values enter the
    artifacts, so identical inputs yield identical outputs (idempotent
    replays).
    """
    if not isinstance(event, dict):
        raise EventValidationError("event must be a JSON object")

    normalized = normalize_event(event)

    try:
        jsonschema.validate(
            normalized,
            load_schema("event.schema.json"),
            format_checker=jsonschema.FormatChecker(),
        )
    except jsonschema.ValidationError as exc:
        raise EventValidationError(
            f"event failed contracts/event.schema.json: {exc.message}"
        ) from exc

    if execution_trace_id is None:
        trace_id = derive_execution_trace_id(normalized["event_id"])
    else:
        trace_id = str(execution_trace_id)
        if not re.fullmatch(r"TRC-[A-Za-z0-9-]+", trace_id):
            raise EventValidationError(
                "execution_trace_id must match ^TRC-[A-Za-z0-9-]+$; "
                f"got {trace_id!r}"
            )

    plan = _build_coverage_plan(normalized, trace_id)
    try:
        jsonschema.validate(plan, load_schema("coverage-plan.schema.json"))
    except jsonschema.ValidationError as exc:  # pragma: no cover
        raise RuntimeError(
            "generated CoveragePlan failed contracts/coverage-plan.schema.json: "
            f"{exc.message}"
        ) from exc

    return {
        "event": normalized,
        "coverage_plan": plan,
        "execution_trace_id": plan["execution_trace_id"],
    }


def persist_artifacts(acquired, directory):
    """Write acquired artifacts to ``directory`` as canonical JSON.

    Durability helper for the Phase 1 exit criterion ("one event accepted
    as a durable, schema-valid artifact").  Writes
    ``<event_id>.event.json`` and ``<event_id>.coverage-plan.json``;
    returns the written paths.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    event_id = acquired["event"]["event_id"]
    written = []
    for suffix, artifact in (
        ("event", acquired["event"]),
        ("coverage-plan", acquired["coverage_plan"]),
    ):
        path = directory / f"{event_id}.{suffix}.json"
        path.write_text(
            json.dumps(artifact, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        written.append(path)
    return written
