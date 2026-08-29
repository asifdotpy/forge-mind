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
        return "ok", "✓", "Autonomous Action Authorized", explain
    if state == "human_review":
        explain = (
            "ForgeMind analyzed this situation and determined that human "
            "authority is needed before taking action."
        )
        return "info", "ℹ", "Human Review Required", explain
    if av:
        explain = (
            "The safety gate applied — human authority is required before "
            "this action can execute."
        )
        return "info", "ℹ", "Safety Gate Applied", explain
    explain = (
        "ForgeMind escalated this situation for human review: "
        f"{_esc(esc.get('summary') or reason)}"
    )
    return "review", "ⓘ", "Escalated to Human Review", explain


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
            + '<p class="gate-answer"><strong>Why is human review needed?'
              f"</strong> {_esc(reason)}</p></section>"
        )
    pr = av.get("policy_result")
    tone = {"allowed": "ok", "requires_human": "info",
            "rejected": "danger"}.get(str(pr), "info")
    checks_html = "".join(
        "<li class=\"check {}\">"
        "<span class=\"glyph\" aria-hidden=\"true\">{}</span>"
        "<div><div class=\"cname\">{}<span class=\"tag\">{}</span></div>"
        "<div class=\"cdetail\">{}</div></div></li>".format(
            "pass" if chk.get("passed") else "fail",
            "✓" if chk.get("passed") else "✕",
            _esc(chk.get("check")),
            "passed" if chk.get("passed") else "requires authority",
            _esc(chk.get("detail")),
        )
        for chk in (av.get("checks") or [])
    ) or '<p class="none-note">No individual checks were reported.</p>'
    answer = ""
    if pr == "requires_human":
        answer = (
            '<p class="gate-answer"><strong>Why is human review needed?'
            "</strong> Because executing this action requires human authority "
            "per policy.</p>"
        )
    return (
        '<section class="card" id="safety-gate">' + heading
        + '<div class="gate-verdict">'
        + f'<span class="pill {tone}">{_esc(pr)}</span>'
        + '<span>validation <span class="mono\">'
        + f"{_esc(av.get('validation_id'))}</span></span></div>"
        + f'<ul class="checks">{checks_html}</ul>' + answer + "</section>"
    )


def _what_happened_section(proof: Dict[str, Any], artifacts: Dict[str, Any]) -> str:
    """Plain-language explanation of why the system made this decision."""
    unc = proof["uncertainty_summary"]
    ctl = proof["human_control_state"]
    conf_pct = _pct(unc.get("confidence"))
    caus = unc.get("causality_status")
    caus_note = _CAUSALITY_NOTES.get(str(caus), "") if caus else ""

    vs = artifacts.get("validated_situation") or {}
    cov = vs.get("coverage") or {}
    provided = cov.get("provided_domains") or []
    missing = cov.get("missing_domains") or []
    total = len(provided) + len(missing)

    shards = artifacts.get("evidence_shards") or []
    findings = artifacts.get("domain_findings") or []

    parts = []
    parts.append(
        f"ForgeMind analyzed {len(shards)} evidence shard"
        f"{'s' if len(shards) != 1 else ''} across {len(findings)} domain"
        f"{'s' if len(findings) != 1 else ''}."
    )
    parts.append(
        f"Confidence: {conf_pct} — evaluated against the decision policy "
        f"(escalate below {_GAUGE_ESCALATE_PCT}%; autonomous at or above "
        f"{_GAUGE_AUTONOMOUS_PCT}%)."
    )
    if caus_note:
        parts.append(f"Causality: {_esc(caus)} — {_esc(caus_note)}.")
    if total:
        parts.append(
            f"Coverage: {len(provided)} of {total} planned domains analyzed."
        )
    state = ctl.get("state")
    if state == "automated":
        parts.append("Result: All safety checks passed — action authorized.")
    elif state == "escalated":
        parts.append("Result: Situation escalated for human review.")
    else:
        parts.append("Result: Human review required before autonomous action.")

    items = "".join(f"<li>{_esc(p)}</li>" for p in parts)
    return (
        '<section class="card" id="what-happened">'
        '<h2 class="label">what happened</h2>'
        '<p class="subtle">A plain-language summary of how ForgeMind '
        "reached this decision.</p>"
        f"<ul class=\"wh-list\">{items}</ul>"
        "</section>"
    )


def _next_steps_section(proof: Dict[str, Any]) -> str:
    """Clear call-to-action: what the user should do next."""
    ctl = proof["human_control_state"]
    state = ctl.get("state")
    role = ctl.get("required_human_role")

    if state == "automated":
        steps = [
            "Review the evidence chain and metrics below to confirm the decision.",
            "No further action required — the action is authorized to execute.",
        ]
    elif state == "escalated":
        steps = [
            "Review the evidence chain and coverage gaps below.",
            f"A designated {_dash(role)} will assess the situation.",
            "Provide additional context to improve future decisions.",
        ]
    else:
        steps = [
            "Review the evidence chain and safety gate checks below.",
            "Approve or reject the proposed action.",
            "Provide additional context to improve future decisions.",
        ]

    items = "".join(f"<li>{_esc(s)}</li>" for s in steps)
    return (
        '<section class="card" id="next-steps">'
        '<h2 class="label">next steps</h2>'
        '<p class="subtle">What you can do with this decision.</p>'
        f"<ul class=\"ns-list\">{items}</ul>"
        "</section>"
    )


def _approval_section(proof: Dict[str, Any], result: Dict[str, Any]) -> str:
    """Interactive approval section for human_review state.

    Shows Approve/Reject buttons with the pending_approval token.
    """
    ctl = proof["human_control_state"]
    state = ctl.get("state")
    pending = result.get("pending_approval") or {}
    token = pending.get("token") or ""
    resume_endpoint = pending.get("resume_endpoint") or ""

    if state == "automated":
        return (
            '<section class="card" id="approval">'
            '<h2 class="label">approval</h2>'
            '<p class="subtle">This action was authorized autonomously.</p>'
            '<p class="approval-status ok">✓ Action authorized — no human approval required.</p>'
            "</section>"
        )

    if state == "escalated":
        return (
            '<section class="card" id="approval">'
            '<h2 class="label">approval</h2>'
            '<p class="subtle">This situation was escalated for human review.</p>'
            '<p class="approval-status">ⓘ Escalated — awaiting human assessment.</p>'
            "</section>"
        )

    # human_review state
    if not token:
        return (
            '<section class="card" id="approval">'
            '<h2 class="label">approval</h2>'
            '<p class="subtle">Human review is required.</p>'
            '<p class="approval-status">No pending approval token available.</p>'
            "</section>"
        )

    approve_url = f"/api/v1/approvals/{token}"
    reject_url = f"/api/v1/approvals/{token}"

    return (
        '<section class="card" id="approval">'
        '<h2 class="label">approval</h2>'
        '<p class="subtle">Approve or reject the proposed action.</p>'
        '<div class="approval">'
        f'<a class="btn-approve" href="{approve_url}?decision=approve">✓ Approve</a>'
        f'<a class="btn-reject" href="{reject_url}?decision=reject">✕ Reject</a>'
        "</div>"
        f'<div class="token-display">Token: {_esc(token)}</div>'
        "</section>"
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
