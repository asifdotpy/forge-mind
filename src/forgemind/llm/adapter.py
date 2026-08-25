"""Gemini 3.5 (Vertex AI) adapter for bounded free-text evidence synthesis.

ADR-010 scope ONLY.  This module is the single point where a model may
influence the pipeline.  Its contract is deliberately narrow:

    generate_observations(domain, context, *, model="gemini-3.5-flash")
        -> list[str] | None
    generate_claims(domain, context, *, model="gemini-3.5-flash")
        -> list[str] | None

Return semantics (FAIL-CLOSED by design):

* A non-``None`` value is a list of 1..N short, groundable strings derived
  ONLY from ``context``.  The caller treats them as ``observations`` /
  ``claims`` text — never as schema-authoritative data.
* ``None`` is the sentinel meaning "no model output available" — the caller
  MUST fall back to its deterministic extraction.  ``None`` is returned when:
    - no Vertex credentials are configured, OR
    - the ``google-genai`` package is not importable, OR
    - ANY error occurs during the call (network, auth, parse, quota...).

Because the only failure mode that reaches the pipeline is "use the
deterministic path", a Gemini outage can NEVER crash the pipeline or forge
a schema-invalid / provenance-less artifact.

``google.genai`` is imported LAZILY inside the functions; the module itself
imports nothing beyond the standard library, so it loads cleanly offline and
the ADR-009 import-boundary test stays green without the dependency.
"""

from __future__ import annotations

import os
from typing import List, Optional

__all__ = ["generate_observations", "generate_claims", "DEFAULT_MODEL"]

#: Default Gemini model (Gemini 3.5 Flash — cheapest 3.5 tier on Vertex).
DEFAULT_MODEL = "gemini-3.5-flash"

#: Hard caps so a runaway model response can never blow up a shard.
_MAX_ITEMS = 25
_MAX_ITEM_LEN = 500

#: Credentials we read (env only — never committed; see ADR-010 guardrails).
_PROJECT_ENV = ("VERTEX_PROJECT", "GOOGLE_CLOUD_PROJECT")
_API_KEY_ENV = ("GOOGLE_API_KEY",)
_LOCATION_ENV = ("GOOGLE_CLOUD_LOCATION", "VERTEX_LOCATION")


def _resolve_credentials() -> tuple[Optional[str], Optional[str], str]:
    """Return ``(project, api_key, location)`` from the environment.

    ``project`` is required for any Vertex call; ``api_key`` selects API-key
    auth over Application Default Credentials (ADC).  Returns an empty
    ``project`` when unconfigured so callers can short-circuit to the
    deterministic fallback without touching the network.
    """
    project = next(
        (os.environ.get(name) for name in _PROJECT_ENV if os.environ.get(name)),
        None,
    )
    api_key = next(
        (os.environ.get(name) for name in _API_KEY_ENV if os.environ.get(name)),
        None,
    )
    location = next(
        (os.environ.get(name) for name in _LOCATION_ENV if os.environ.get(name)),
        None,
    ) or "us-central1"
    return project, api_key, location


def _build_prompt(kind: str, domain: str, context: dict) -> str:
    """Construct a tightly-bounded prompt for one evidence kind.

    The model is instructed to stay inside ``context`` (the bounded domain
    inputs), return ONLY terse strings, and never invent cross-domain
    reasoning.  ``kind`` is ``"observations"`` or ``"claims"``.
    """
    inputs = context.get("inputs") or {}
    inputs_repr = "\n".join(f"  - {k}: {v!r}" for k, v in inputs.items()) or "  (none)"
    role = {
        "observations": (
            "concrete, factual observations about the supplied code-domain "
            "inputs (e.g. which files changed, CI outcome, scan results)"
        ),
        "claims": (
            "defensible, citation-grounded claims the supplied code-domain "
            "inputs support (no speculation beyond the inputs)"
        ),
    }[kind]
    return (
        f"You are a senior software engineer performing bounded code-domain "
        f"evidence synthesis for the domain '{domain}'.\n"
        f"Produce {role}.\n"
        f"Ground EVERY line strictly in the supplied inputs below; do not "
        f"reference anything outside them, do not invent file names, and do "
        f"not perform cross-domain reasoning.\n\n"
        f"Supplied inputs (this is the ONLY source of truth):\n{inputs_repr}\n\n"
        f"Return {_MAX_ITEMS} or fewer short lines. Each line must be a single "
        f"self-contained observation/claim. Do NOT use markdown, bullets, or "
        f"numbering — one plain sentence per line."
    )


def _parse_lines(text: str) -> Optional[List[str]]:
    """Split model text into a clean list of short strings, or ``None``.

    Strips leading bullets / numbering / whitespace.  Returns ``None`` when
    nothing usable came back so the caller keeps its deterministic output.
    """
    if not text:
        return None
    cleaned: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        # Drop bullet / numbered prefixes: "-", "*", "1.", "1)".
        while line and line[0] in "-*":
            line = line[1:].strip()
        while line and line[0:1].isdigit():
            rest = line[1:].strip()
            if rest and rest[0] in ".)":
                line = rest[1:].strip()
                break
            break
        if not line:
            continue
        if len(line) > _MAX_ITEM_LEN:
            line = line[:_MAX_ITEM_LEN].rstrip() + "…"
        cleaned.append(line)
        if len(cleaned) >= _MAX_ITEMS:
            break
    if not cleaned:
        return None
    return cleaned


def _generate(kind: str, domain: str, context: dict, model: str) -> Optional[List[str]]:
    """Core Gemini call.  Returns a string list or ``None`` (never raises)."""
    project, api_key, location = _resolve_credentials()
    if not project:
        return None  # No credentials -> deterministic fallback.
    try:
        # Lazily imported so the package is optional at import time.
        from google import genai  # type: ignore

        if api_key:
            client = genai.Client(api_key=api_key)
        else:
            # Vertex AI path: relies on Application Default Credentials.
            client = genai.Client(vertexai=True, project=project, location=location)

        response = client.models.generate_content(
            model=model,
            contents=_build_prompt(kind, domain, context),
        )
        text = getattr(response, "text", None)
        if text is None and getattr(response, "candidates", None):
            text = "".join(
                part.text
                for part in response.candidates[0].content.parts
                if getattr(part, "text", None)
            )
        return _parse_lines(text or "")
    except Exception:
        # Fail-closed: ANY model/network/auth/parse error degrades to the
        # deterministic path.  Never surface the exception into the pipeline.
        return None


def generate_observations(
    domain: str, context: dict, *, model: str = DEFAULT_MODEL
) -> Optional[List[str]]:
    """Model-backed ``observations`` text, or ``None`` to fall back.

    See module docstring for the fail-closed contract.  The output is free
    text only; it is never treated as schema- or provenance-authoritative.
    """
    return _generate("observations", domain, context, model)


def generate_claims(
    domain: str, context: dict, *, model: str = DEFAULT_MODEL
) -> Optional[List[str]]:
    """Model-backed ``claims`` text, or ``None`` to fall back.

    Mirrors :func:`generate_observations` for the ``claims`` evidence kind.
    """
    return _generate("claims", domain, context, model)
