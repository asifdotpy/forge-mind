from __future__ import annotations

"""Small, dependency-free HTML rendering helpers."""
from typing import Any

def _esc(value: Any) -> str:
    """Minimal HTML escaping for untrusted artifact values."""
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _dash(value: Any) -> str:
    """Escape ``value``, rendering absent values as an honest em dash."""
    if value is None or value == "" or value == []:
        return '<span class="none-note">—</span>'
    if isinstance(value, (list, tuple)):
        joined = ", ".join(str(v) for v in value)
        return f'<span class="mono">{_esc(joined)}</span>'
    return f'<span class="mono">{_esc(value)}</span>'


def _pct(value: Any) -> str:
    """Format a 0.0-1.0 confidence float as a percentage string."""
    try:
        return f"{round(float(value) * 100)}%"
    except (TypeError, ValueError):
        return "—"


def _risk_pill(risk_level: Any) -> str:
    """Render ``risk_level`` with semantic tone (never colour alone)."""
    tone = {"low": "ok", "medium": "warn", "high": "danger",
            "critical": "danger"}.get(str(risk_level), "info")
    label = risk_level if risk_level not in (None, "") else "unknown"
    return f'<span class="pill {tone}">{_esc(label)}</span>'
