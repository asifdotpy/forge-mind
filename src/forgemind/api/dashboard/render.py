from __future__ import annotations

"""Assemble the full judge-visible HTML document from one pipeline result."""
from typing import Any, Dict

from forgemind.api.dashboard.css import _VIEWER_CSS
from forgemind.api.dashboard.helpers import _esc, _pct, _risk_pill
from forgemind.api.dashboard.sections import (
    _chain_section,
    _control_section,
    _evidence_section,
    _gate_section,
    _hero_state,
    _what_happened_section,
    _next_steps_section,
    _approval_section,
    _uncertainty_section,
)
from forgemind.api.errors import SERVICE_VERSION
from forgemind.m3_proof import build_m3_proof

#: Default fixture situation rendered by the read-only viewer (M3-A / T721).
DEFAULT_VIEWER_SITUATION_ID = "SIT-1000"

def _render_situation_html(result: Dict[str, Any]) -> str:
    """Render the read-only M3 judge surface (T721 redesign).

    Reads ONLY ``build_m3_proof`` output plus the canonical artifacts carried
    by the pipeline result — no tier logic is re-implemented here.
    """
    proof = result.get("m3_proof") or build_m3_proof(result)
    links = proof["provenance_links"]
    uncertainty = proof["uncertainty_summary"]
    control = proof["human_control_state"]
    artifacts = result.get("artifacts") or {}
    terminal = result.get("terminal") or {}

    hero_cls, hero_glyph, hero_label, hero_explain = _hero_state(
        proof, terminal
    )
    conf_pct = _pct(uncertainty.get("confidence"))
    vs = artifacts.get("validated_situation") or {}
    cov = vs.get("coverage") or {}
    pct_raw = cov.get("coverage_percentage")
    cov_dd = (_esc(f"{pct_raw}%")
              if isinstance(pct_raw, (int, float))
              else '<span class="none-note">—</span>')
    caus = uncertainty.get("causality_status")
    metrics = "".join(
        f"<div><dt>{t}</dt><dd>{v}</dd></div>"
        for t, v in (
            ("confidence", _esc(conf_pct)),
            ("coverage", cov_dd),
            ("risk", _risk_pill(control.get("risk_level"))),
            ("causality",
             f'<span class="chip-mini">{_esc(caus or "unknown")}</span>'),
        )
    )
    hero = (
        f'<section class="card hero {hero_cls}" aria-labelledby="verdict-h">'
        '<div class="eyebrow"><span>pipeline outcome</span>'
        '<span class="mono">'
        f"{_esc(links.get('execution_trace_id'))} · "
        f"{_esc(links.get('situation_id'))}"
        "</span></div>"
        '<h2 class="verdict" id="verdict-h">'
        f'<span class="glyph" aria-hidden="true">{hero_glyph}</span>'
        f"{_esc(hero_label)}</h2>"
        f'<p class="explain">{hero_explain}</p>'
        f'<dl class="metrics">{metrics}</dl>'
        '<a class="btn" href="#trace">View evidence chain ↓</a></section>'
    )
    gate = _gate_section(terminal, proof)
    what_happened_sec = _what_happened_section(proof, artifacts)
    next_steps_sec = _next_steps_section(proof)
    approval_sec = _approval_section(proof, result)
    chain_sec = _chain_section(links, terminal)
    evidence_sec = _evidence_section(artifacts)
    uncertainty_sec = _uncertainty_section(proof)
    control_sec = _control_section(proof)
    css = _VIEWER_CSS
    title_sid = _esc(links.get("situation_id") or "situation")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>ForgeMind · {title_sid} · judge surface</title>
<style>{css}</style>
</head>
<body>
<div class="wrap">

<header class="site">
  <span class="brand">ForgeMind</span>
  <span class="site-meta">
    <span class="chip">SPEC-001 · M3</span>
    <span class="chip dim">read-only · offline snapshot</span>
    <span class="chip dim mono">v{_esc(SERVICE_VERSION)}</span>
  </span>
  <p class="tagline">Engineering Intelligence &amp; Decision Runtime — a deterministic replay of one pipeline execution.</p>
</header>

<main>
{hero}
{what_happened_sec}
{gate}
{approval_sec}
{next_steps_sec}
{chain_sec}
<div class="grid2">
{evidence_sec}
{uncertainty_sec}
</div>
{control_sec}
</main>

<footer class="site">
  <span>ForgeMind</span>
  <span>SPEC-001 · M3-A (T721)</span>
  <span>situation <span class="mono">{_esc(links.get('situation_id'))}</span></span>
  <span>trace <span class="mono">{_esc(links.get('execution_trace_id'))}</span></span>
  <span>v{_esc(SERVICE_VERSION)}</span>
  <span>read-only · offline snapshot</span>
</footer>

</div>
</body>
</html>
"""
