from __future__ import annotations

"""Judge-visible dashboard (M3-A / T721) - offline, read-only HTML viewer.

Renders the four M3 properties (provenance, validation, uncertainty, human
control) from ``build_m3_proof`` output only - no tier logic is re-implemented."""
from forgemind.api.dashboard.render import (
    DEFAULT_VIEWER_SITUATION_ID,
    _render_situation_html,
)

__all__ = ["DEFAULT_VIEWER_SITUATION_ID", "_render_situation_html"]
