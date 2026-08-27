from __future__ import annotations

"""Section renderers for the M3 judge surface (presentation only)."""
from typing import Any, Dict

from forgemind.api.dashboard.constants import (
    _ARTIFACT_LABELS,
    _CAUSALITY_NOTES,
    _GAUGE_AUTONOMOUS_PCT,
    _GAUGE_ESCALATE_PCT,
)
from forgemind.api.dashboard.helpers import _dash, _esc, _pct, _risk_pill
from forgemind.api.errors import SERVICE_VERSION

def _hero_state(
    proof: Dict[str, Any], terminal: Dict[str, Any]
) -> tuple:
    """Translate M3 proof enums into hero copy (tone/glyph/label/explain).

    Presentation-only mapping of runtime states - no policy evaluation.
    """
    verdict = proof["validation_verdict"]
    av = terminal.get("action_validation") or {}
    esc = terminal.get("escalation") or {}
    state = verdict.get("state")
    reason = verdict.get("reason") or esc.get("reason") or ""
    action_id = av.get("action_id")

    if state == "automated":
        explain = (
            f"Proposed action {_dash(action_id)} passed the safety gate "
            f"(policy result: {_esc(verdict.get('policy_result'))}) and is "
            "authorized to execute autonomously."
        )
        return "ok", "✓", "AUTONOMOUS ACTION AUTHORIZED", explain
    if state == "human_review":
        explain = (
            f"Proposed action {_dash(action_id)} was withheld by the safety "
            f"gate: {_esc(reason)} Executing it requires human authority."
        )
        return "warn", "⚠", "HUMAN APPROVAL REQUIRED", explain
    if av:
        explain = (
            "No autonomous execution - the safety gate stopped the proposed "
            f"action: {_esc(reason)}"
        )
        return "danger", "✕", "ACTION BLOCKED BY SAFETY GATE", explain
    explain = (
        "No action was proposed - ForgeMind escalated the situation for "
        f"human review: {_esc(esc.get('summary') or reason)}"
    )
    return "danger", "!", "ESCALATED TO HUMAN", explain


def _gate_section(terminal: Dict[str, Any], proof: Dict[str, Any]) -> str:
    """First-class Safety Gate panel rendering ``action_validation.checks``."""
    verdict = proof["validation_verdict"]
    av = terminal.get("action_validation") or {}
    heading = '<h2 class="label">safety gate · action validation</h2>'
    if not av:
        reason = verdict.get("reason") or ""
        return (
            '<section class="card" id="safety-gate">' + heading
            + '<p class="subtle">No action reached the safety gate in this '
              "run — ForgeMind escalated before proposing an action.</p>"
            + '<p class="gate-answer"><strong>Why didn&#39;t ForgeMind act?'
              f"</strong> {_esc(reason)}</p></section>"
        )
    pr = av.get("policy_result")
    tone = {"allowed": "ok", "requires_human": "warn",
            "rejected": "danger"}.get(str(pr), "info")
    checks_html = "".join(
        "<li class=\"check {}\">"
        "<span class=\"glyph\" aria-hidden=\"true\">{}</span>"
        "<div><div class=\"cname\">{}<span class=\"tag\">{}</span></div>"
        "<div class=\"cdetail\">{}</div></div></li>".format(
            "pass" if chk.get("passed") else "fail",
            "✓" if chk.get("passed") else "✕",
            _esc(chk.get("check")),
            "passed" if chk.get("passed") else "blocked",
            _esc(chk.get("detail")),
        )
        for chk in (av.get("checks") or [])
    ) or '<p class="none-note">No individual checks were reported.</p>'
    answer = ""
    if pr == "requires_human":
        answer = (
            '<p class="gate-answer"><strong>Why didn&#39;t ForgeMind '
            "execute the action?</strong> Because executing it requires "
            "human authority.</p>"
        )
    return (
        '<section class="card" id="safety-gate">' + heading
        + '<div class="gate-verdict">'
        + f'<span class="pill {tone}">{_esc(pr)}</span>'
        + '<span>validation <span class="mono">'
        + f"{_esc(av.get('validation_id'))}</span></span></div>"
        + f'<ul class="checks">{checks_html}</ul>' + answer + "</section>"
    )


def _metadata_rows(links: Dict[str, Any]) -> str:
    """Key/value rows for the execution-metadata <details> block."""
    chain = {e.get("artifact"): e.get("id")
             for e in (links.get("artifact_chain") or [])}
    rows = (
        ("Execution trace", links.get("execution_trace_id")),
        ("Situation", links.get("situation_id")),
        ("Event", links.get("event_id")),
        ("Coverage plan", links.get("coverage_plan_id")),
        ("Decision record", chain.get("decision_record")),
        ("Action validation", chain.get("action_validation")),
        ("Terminal", chain.get("terminal")),
        ("Service version", SERVICE_VERSION),
    )
    return "".join(f"<dt>{_esc(k)}</dt><dd>{_dash(v)}</dd>" for k, v in rows)


def _node(label: str, aid: Any, note: str = "", cls: str = "") -> str:
    """One provenance-chain node: artifact type, ID, optional count note."""
    note_html = f'<span class="nnote">{_esc(note)}</span>' if note else ""
    klass = f"node {cls}" if cls else "node"
    return (f'<li class="{klass}"><span class="ntype">{_esc(label)}</span>'
            f"{_dash(aid)}{note_html}</li>")

def _chain_section(links: Dict[str, Any], terminal: Dict[str, Any]) -> str:
    """Provenance chain: horizontal on desktop, vertical timeline on mobile."""
    nodes = [_node("Event", links.get("event_id"), "origin")]
    for entry in links.get("artifact_chain") or []:
        name = entry.get("artifact") or ""
        aid = entry.get("id")
        note, cls = "", ""
        if name == "evidence_shards":
            if isinstance(aid, (list, tuple)):
                n = len(aid)
                note = f"{n} shard{'s' if n != 1 else ''} produced"
                aid = ", ".join(str(a) for a in aid) if aid else None
            elif isinstance(aid, int):
                note = f"{aid} shards produced"
                aid = str(aid)
        elif name == "domain_findings":
            if isinstance(aid, (list, tuple)):
                n = len(aid)
                note = f"{n} finding{'s' if n != 1 else ''} produced"
                aid = ", ".join(str(a) for a in aid) if aid else None
        elif name == "action_validation":
            cls = "gate"
        elif name == "terminal":
            note = str(terminal.get("type") or "")
        label = _ARTIFACT_LABELS.get(name, name.replace("_", " ").title())
        nodes.append(_node(label, aid, note, cls))
    joined = '<li class="join" aria-hidden="true">→</li>'.join(nodes)
    return (
        '<section class="card" id="trace">'
        '<h2 class="label">traceable decision · provenance chain</h2>'
        '<p class="subtle">Every decision can be traced back to its '
        'originating event — absence stays visible, never hidden.</p>'
        f'<ol class="chain">{joined}</ol>'
        '<details class="meta-block"><summary>Execution metadata</summary>'
        f'<dl class="kv">{_metadata_rows(links)}</dl></details>'
        "</section>"
    )


def _evidence_section(artifacts: Dict[str, Any]) -> str:
    """Evidence produced: shards, findings and coverage — with real IDs."""
    vs = artifacts.get("validated_situation") or {}
    cov = vs.get("coverage") or {}
    provided = cov.get("provided_domains") or []
    missing = cov.get("missing_domains") or []
    total = len(provided) + len(missing)

    shards = artifacts.get("evidence_shards") or []
    shard_ids = [s.get("evidence_shard_id") for s in shards
                 if s.get("evidence_shard_id")]
    if shard_ids:
        shard_block = ('<ul class="ids">'
                       + "".join(f"<li>{_esc(i)}</li>" for i in shard_ids)
                       + "</ul>")
        plural = "s" if len(shards) != 1 else ""
        shard_count = f"{len(shards)} EvidenceShard{plural}"
    else:
        shard_block = ('<p class="none-note">None produced in this run — the '
                       "gap stays visible downstream.</p>")
        shard_count = "no EvidenceShards"

    findings = artifacts.get("domain_findings") or []
    if findings:
        rows = "".join(
            "<li>{}{}</li>".format(
                _esc(f.get("finding_id")),
                f' · domain {_esc(f.get("domain"))}'
                if f.get("domain") else "",
            )
            for f in findings
        )
        finding_block = f'<ul class="ids">{rows}</ul>'
        plural = "s" if len(findings) != 1 else ""
        finding_count = f"{len(findings)} DomainFinding{plural}"
    else:
        finding_block = '<p class="none-note">None produced in this run.</p>'
        finding_count = "no DomainFindings"

    pct = cov.get("coverage_percentage")
    cov_title = f"{pct}%" if isinstance(pct, (int, float)) else "—"
    cov_count = (f"{len(provided)} of {total} planned domains"
                 if total else "planned domains not reported")
    chips = "".join(f'<span class="chip-mini">{_esc(d)}</span>'
                    for d in provided)
    chips += "".join('<span class="chip-mini miss">missing: '
                     f"{_esc(d)}</span>" for d in missing)
    chips_block = f'<div class="dom-chips">{chips}</div>' if chips else ""
    return (
        '<section class="card"><h2 class="label">evidence</h2>'
        '<ul class="evi">'
        '<li><div class="etitle">Evidence produced '
        f'<span class="ecount">· {shard_count}</span></div>{shard_block}</li>'
        '<li><div class="etitle">Domain analysis '
        f'<span class="ecount">· {finding_count}'
        f"</span></div>{finding_block}</li>"
        '<li><div class="etitle">Coverage '
        f'<span class="ecount">· {cov_title} · {cov_count}</span></div>'
        f"{chips_block}</li></ul></section>"
    )

def _uncertainty_section(proof: Dict[str, Any]) -> str:
    """Confidence gauge vs the reducer-owned ladder, plus explicit unknowns."""
    unc = proof["uncertainty_summary"]
    conf_pct = _pct(unc.get("confidence"))
    try:
        fill = min(100.0, max(0.0, float(unc.get("confidence")) * 100.0))
    except (TypeError, ValueError):
        fill = 0.0
    gauge_label = (f"Confidence {conf_pct}. Policy ladder: escalate below "
                   f"{_GAUGE_ESCALATE_PCT} percent; autonomous at or above "
                   f"{_GAUGE_AUTONOMOUS_PCT} percent.")
    caus = unc.get("causality_status")
    if caus:
        note = _CAUSALITY_NOTES.get(str(caus))
        caus_line = ('<p class="gauge-cap">Causality <span class='
                     f'"chip-mini warn-text">{_esc(caus)}</span>'
                     + (f" — {_esc(note)}" if note else "") + "</p>")
    else:
        caus_line = '<p class="gauge-cap">Causality status not reported.</p>'
    items = unc.get("uncertainties") or []
    if items:
        unc_block = ('<ul class="unc-list">'
                     + "".join(f"<li>{_esc(u)}</li>" for u in items) + "</ul>")
    else:
        unc_block = ('<p class="none-note">No additional uncertainties '
                     'recorded.</p>')
    return (
        '<section class="card">'
        '<h2 class="label">uncertainty &amp; confidence</h2>'
        '<p class="gauge-cap"><strong>' + _esc(conf_pct) + "</strong> "
        "situation confidence, evaluated against an explicit decision policy"
        "</p>"
        f'<div class="gauge" role="img" aria-label="{_esc(gauge_label)}">'
        f'<div class="gauge-fill" style="width:{fill:.1f}%"></div>'
        f'<div class="gauge-tick" style="left:{_GAUGE_ESCALATE_PCT}%"></div>'
        f'<div class="gauge-tick" style="left:{_GAUGE_AUTONOMOUS_PCT}%"></div>'
        "</div>"
        '<div class="gauge-note">'
        f"<span>escalate &lt; {_GAUGE_ESCALATE_PCT}%</span>"
        f"<span>autonomous ≥ {_GAUGE_AUTONOMOUS_PCT}%</span>"
        "</div>" + caus_line + unc_block + "</section>"
    )

def _control_section(proof: Dict[str, Any]) -> str:
    """Human-control panel: authority, autonomy class, risk, decision owner."""
    ctl = proof["human_control_state"]
    automated = ctl.get("state") == "automated"
    human_decision = "Not required" if automated else "Required"
    principle = (
        "The action stayed inside the authorized boundary: every safety check"
        " passed and policy allowed autonomous execution."
        if automated else
        "ForgeMind can recommend an action, but authorization remains outside"
        " autonomous execution."
    )
    flow = ("AI proposes → safety gate validates → human authority controls "
            "execution")
    return (
        '<section class="card"><h2 class="label">human control</h2>'
        '<dl class="kv">'
        "<dt>Required authority</dt>"
        f"<dd>{_dash(ctl.get('required_human_role'))}</dd>"
        "<dt>Autonomy class</dt>"
        f"<dd>{_dash(ctl.get('autonomy_class'))}</dd>"
        f"<dt>Risk level</dt><dd>{_risk_pill(ctl.get('risk_level'))}</dd>"
        f"<dt>Human decision</dt><dd>{_esc(human_decision)}</dd>"
        "</dl>"
        f'<p class="principle">{_esc(principle)}<br>{_esc(flow)}</p>'
        "</section>"
    )
