from __future__ import annotations

"""Pure-SVG chart renderers for the dashboard (no external dependencies).

Produces inline SVG strings for:
- Evidence distribution (horizontal bar chart by domain/evidence_state)
- Confidence trend (sparkline + area chart across artifact stages)

All functions are deterministic pure functions of their inputs.
"""
from typing import Any, Dict, List, Optional

from forgemind.api.dashboard.helpers import _esc


def _evidence_distribution_data(artifacts: Dict[str, Any]) -> Dict[str, int]:
    """Count evidence states across all shards and findings."""
    counts: Dict[str, int] = {
        "observed": 0,
        "no_signal": 0,
        "verified": 0,
        "unavailable": 0,
        "contradictory": 0,
    }
    shards = artifacts.get("evidence_shards") or []
    for shard in shards:
        structured = shard.get("structured_claims") or []
        for claim in structured:
            state = claim.get("evidence_state", "observed")
            if state in counts:
                counts[state] += 1
            else:
                counts["observed"] += 1
        # Also count raw claims if no structured claims present
        if not structured:
            for claim in (shard.get("claims") or []):
                if isinstance(claim, dict):
                    state = claim.get("evidence_state", "observed")
                else:
                    lowered = str(claim).lower()
                    state = (
                        "no_signal"
                        if any(p in lowered for p in ("no ", "no signal", "nothing found", "no evidence"))
                        else "observed"
                    )
                if state in counts:
                    counts[state] += 1
                else:
                    counts["observed"] += 1
    return counts


def evidence_distribution_chart(artifacts: Dict[str, Any]) -> str:
    """Render a horizontal bar chart of evidence states (SVG, no deps)."""
    counts = _evidence_distribution_data(artifacts)
    total = sum(counts.values())

    if total == 0:
        return '<p class="none-note">No evidence recorded in this run.</p>'

    # Color map matching CSS theme
    colors = {
        "observed": "var(--ok)",
        "no_signal": "var(--muted)",
        "verified": "var(--info)",
        "unavailable": "var(--warn)",
        "contradictory": "var(--danger)",
    }
    labels = {
        "observed": "Observed",
        "no_signal": "No Signal",
        "verified": "Verified",
        "unavailable": "Unavailable",
        "contradictory": "Contradictory",
    }

    bar_h = 22
    bar_gap = 8
    label_w = 110
    bar_max = 280
    svg_h = len(counts) * (bar_h + bar_gap) + 4
    svg_w = label_w + bar_max + 50

    rows: List[str] = []
    for i, (state, count) in enumerate(counts.items()):
        pct = count / total
        bar_w = max(2, int(bar_max * pct))
        y = i * (bar_h + bar_gap)
        rows.append(
            f'<g transform="translate(0,{y})">'
            f'<text x="{label_w - 8}" y="{bar_h // 2 + 4}" text-anchor="end" '
            f'font-size="11" fill="var(--text-2)">{_esc(labels[state])}</text>'
            f'<rect x="{label_w}" y="0" width="{bar_w}" height="{bar_h}" rx="4" '
            f'fill="{colors[state]}" opacity="0.85"/>'
            f'<text x="{label_w + bar_w + 6}" y="{bar_h // 2 + 4}" '
            f'font-size="11" fill="var(--text)" font-weight="600">{count}</text>'
            f'</g>'
        )

    return (
        f'<svg viewBox="0 0 {svg_w} {svg_h}" width="100%" height="{svg_h}" '
        f'role="img" aria-label="Evidence distribution: {total} total claims">'
        f'{"".join(rows)}</svg>'
    )


def _confidence_series(result: Dict[str, Any]) -> List[float]:
    """Extract a confidence series across pipeline stages."""
    series: List[float] = []
    artifacts = result.get("artifacts") or {}

    # Stage 1: worker shard confidences (average)
    shards = artifacts.get("evidence_shards") or []
    if shards:
        shard_confs = [float(s.get("confidence", 0.0)) for s in shards]
        series.append(round(sum(shard_confs) / len(shard_confs), 2))
    else:
        series.append(0.0)

    # Stage 2: domain finding confidences (average)
    findings = artifacts.get("domain_findings") or []
    if findings:
        finding_confs = [float(f.get("confidence", 0.0)) for f in findings]
        series.append(round(sum(finding_confs) / len(finding_confs), 2))
    else:
        series.append(0.0)

    # Stage 3: validated situation confidence
    vs = artifacts.get("validated_situation") or {}
    series.append(float(vs.get("confidence", 0.0)))

    # Stage 4: decision record confidence
    terminal = result.get("terminal") or {}
    dr = terminal.get("decision_record") or result.get("decision_record") or {}
    series.append(float(dr.get("confidence", vs.get("confidence", 0.0))))

    return series


def confidence_trend_chart(result: Dict[str, Any]) -> str:
    """Render a sparkline + area chart of confidence across pipeline stages."""
    series = _confidence_series(result)
    labels = ["Workers", "Findings", "Validated", "Decision"]

    if not series or all(v == 0.0 for v in series):
        return '<p class="none-note">No confidence data recorded.</p>'

    svg_w = 360
    svg_h = 120
    pad_l = 32
    pad_b = 22
    pad_t = 10
    pad_r = 8
    plot_w = svg_w - pad_l - pad_r
    plot_h = svg_h - pad_b - pad_t

    # Y-axis: 0..1.0 → plot_h..0
    def y_pos(v: float) -> float:
        return pad_t + plot_h - (max(0.0, min(1.0, v)) * plot_h)

    step_x = plot_w / max(1, len(series) - 1)
    points = [(pad_l + i * step_x, y_pos(v)) for i, v in enumerate(series)]

    # Area path (close to baseline)
    area_path = (
        f"M{points[0][0]:.1f},{points[0][1]:.1f} "
        + " ".join(f"L{x:.1f},{y:.1f}" for x, y in points[1:])
        + f" L{points[-1][0]:.1f},{pad_t + plot_h} L{points[0][0]:.1f},{pad_t + plot_h} Z"
    )
    # Line path
    line_path = (
        f"M{points[0][0]:.1f},{points[0][1]:.1f} "
        + " ".join(f"L{x:.1f},{y:.1f}" for x, y in points[1:])
    )

    # Threshold lines
    esc_y = y_pos(0.5)
    aut_y = y_pos(0.75)

    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="var(--info)" stroke="var(--bg)" stroke-width="1.5"/>'
        for x, y in points
    )

    x_labels = "".join(
        f'<text x="{x:.1f}" y="{svg_h - 6}" text-anchor="middle" '
        f'font-size="9" fill="var(--muted)">{_esc(labels[i])}</text>'
        for i, (x, y) in enumerate(points)
    )

    return (
        f'<svg viewBox="0 0 {svg_w} {svg_h}" width="100%" height="{svg_h}" '
        f'role="img" aria-label="Confidence trend: {", ".join(f"{v:.0%}" for v in series)}">'
        f'<line x1="{pad_l}" y1="{esc_y:.1f}" x2="{svg_w - pad_r}" y2="{esc_y:.1f}" '
        f'stroke="var(--danger)" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.6"/>'
        f'<text x="{svg_w - pad_r}" y="{esc_y - 3}" text-anchor="end" '
        f'font-size="8" fill="var(--danger)" opacity="0.7">escalate 50%</text>'
        f'<line x1="{pad_l}" y1="{aut_y:.1f}" x2="{svg_w - pad_r}" y2="{aut_y:.1f}" '
        f'stroke="var(--ok)" stroke-width="0.5" stroke-dasharray="3,3" opacity="0.6"/>'
        f'<text x="{svg_w - pad_r}" y="{aut_y - 3}" text-anchor="end" '
        f'font-size="8" fill="var(--ok)" opacity="0.7">autonomous 75%</text>'
        f'<path d="{area_path}" fill="var(--info)" opacity="0.12"/>'
        f'<path d="{line_path}" fill="none" stroke="var(--info)" stroke-width="2" stroke-linejoin="round"/>'
        f'{dots}{x_labels}</svg>'
    )


def _coverage_heatmap_data(artifacts: Dict[str, Any]) -> Dict[str, Dict[str, int]]:
    """Build a domain × evidence_state matrix for the coverage heatmap."""
    # Canonical domains in lifecycle order
    domains = ["code", "delivery", "production"]
    states = ["observed", "no_signal", "verified", "unavailable"]

    # Initialize matrix
    matrix: Dict[str, Dict[str, int]] = {d: {s: 0 for s in states} for d in domains}

    shards = artifacts.get("evidence_shards") or []
    for shard in shards:
        domain = shard.get("domain", "unknown")
        if domain not in matrix:
            matrix[domain] = {s: 0 for s in states}

        structured = shard.get("structured_claims") or []
        for claim in structured:
            state = claim.get("evidence_state", "observed")
            if state not in matrix[domain]:
                state = "observed"
            matrix[domain][state] += 1

        # Also count raw claims if no structured claims
        if not structured:
            for claim in (shard.get("claims") or []):
                if isinstance(claim, dict):
                    state = claim.get("evidence_state", "observed")
                else:
                    lowered = str(claim).lower()
                    state = (
                        "no_signal"
                        if any(p in lowered for p in ("no ", "no signal", "nothing found", "no evidence"))
                        else "observed"
                    )
                if state not in matrix[domain]:
                    state = "observed"
                matrix[domain][state] += 1

    return matrix


def coverage_heatmap_chart(artifacts: Dict[str, Any]) -> str:
    """Render a coverage heatmap by domain × evidence state (SVG, no deps)."""
    matrix = _coverage_heatmap_data(artifacts)

    # Filter to domains that have data
    active_domains = [d for d, counts in matrix.items() if sum(counts.values()) > 0]
    if not active_domains:
        return '<p class="none-note">No coverage data recorded.</p>'

    states = ["observed", "no_signal", "verified", "unavailable"]
    state_labels = {
        "observed": "Observed",
        "no_signal": "No Signal",
        "verified": "Verified",
        "unavailable": "Unavailable",
    }

    cell_w = 80
    cell_h = 28
    label_w = 90
    header_h = 24
    svg_w = label_w + len(states) * cell_w + 10
    svg_h = header_h + len(active_domains) * cell_h + 4

    # Color intensity mapping
    def cell_color(state: str, count: int) -> str:
        if count == 0:
            return "var(--surface-2)"
        colors = {
            "observed": f"rgba(52,211,153,{min(0.2 + count * 0.15, 0.9)})",
            "no_signal": f"rgba(113,113,122,{min(0.2 + count * 0.15, 0.7)})",
            "verified": f"rgba(96,165,250,{min(0.2 + count * 0.15, 0.9)})",
            "unavailable": f"rgba(251,191,36,{min(0.2 + count * 0.15, 0.8)})",
        }
        return colors.get(state, "var(--surface-2)")

    def text_color(state: str, count: int) -> str:
        return "var(--text)" if count > 0 else "var(--muted)"

    # Header row (state labels)
    header_cells = []
    for i, state in enumerate(states):
        x = label_w + i * cell_w
        header_cells.append(
            f'<text x="{x + cell_w // 2}" y="{header_h - 8}" text-anchor="middle" '
            f'font-size="9" fill="var(--muted)" font-weight="600">{_esc(state_labels[state])}</text>'
        )

    # Data rows
    rows = []
    for di, domain in enumerate(active_domains):
        y = header_h + di * cell_h
        # Domain label
        rows.append(
            f'<text x="{label_w - 8}" y="{y + cell_h // 2 + 4}" text-anchor="end" '
            f'font-size="11" fill="var(--text-2)">{_esc(domain)}</text>'
        )
        # Cells for each state
        for si, state in enumerate(states):
            count = matrix[domain].get(state, 0)
            x = label_w + si * cell_w
            rows.append(
                f'<rect x="{x}" y="{y}" width="{cell_w}" height="{cell_h}" rx="4" '
                f'fill="{cell_color(state, count)}" stroke="var(--border)" stroke-width="0.5"/>'
                f'<text x="{x + cell_w // 2}" y="{y + cell_h // 2 + 4}" text-anchor="middle" '
                f'font-size="11" fill="{text_color(state, count)}" font-weight="600">{count}</text>'
            )

    return (
        f'<svg viewBox="0 0 {svg_w} {svg_h}" width="100%" height="{svg_h}" '
        f'role="img" aria-label="Coverage heatmap: {len(active_domains)} domains × {len(states)} evidence states">'
        f'{"".join(header_cells)}{"".join(rows)}</svg>'
    )