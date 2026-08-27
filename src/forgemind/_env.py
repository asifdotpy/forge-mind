"""Lightweight ``.env`` loader for local development (no external dependency).

Mirrors the pattern used by ``scripts/sync_notion_brain.py`` so behaviour is
identical across the repo: the gitignored project-root ``.env`` is read once
and any keys not already present in the process environment are applied.
Existing environment variables always win, so shell exports, Cloud Run
platform-injected vars, and test monkeypatches are never overridden.

Safety rails:

* Under pytest the loader is a strict no-op — the test suite must stay
  hermetic and never observe a developer's real ``.env`` secrets (notably
  ``GITHUB_TOKEN``/``NOTION_TOKEN``), otherwise webhook tests would start
  issuing real GitHub writes.
* ``FORGEMIND_SKIP_DOTENV=1`` disables it explicitly.
* Production images (Cloud Run) carry no ``.env`` file, so it silently does
  nothing there and the service keeps using platform-injected env vars.
* Only key *names* are ever returned — never values — so callers can log the
  result safely.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List, MutableMapping, Optional

from forgemind._paths import REPO_ROOT

__all__ = ["load_dotenv"]

#: Set once the (gitignored) ``.env`` has been applied to ``os.environ``.
_loaded: bool = False


def _parse_and_apply(raw: str, environ: MutableMapping[str, str]) -> List[str]:
    """Apply ``KEY=VALUE`` lines from ``raw`` into ``environ``.

    Skips blank lines, ``#`` comments, and lines without ``=``. Strips one
    layer of matching surrounding quotes from values. Keys already present in
    ``environ`` are never overwritten. Returns the applied key names only.
    """
    applied: List[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"").strip()
        if key and key not in environ:
            environ[key] = value
            applied.append(key)
    return applied


def load_dotenv(env_file: Optional[os.PathLike] = None) -> List[str]:
    """Load ``.env`` into ``os.environ`` exactly once (idempotent).

    Args:
        env_file: Explicit ``.env`` path; defaults to ``$FORGEMIND_ENV_FILE``
            or the gitignored ``<repo-root>/.env``.

    Returns:
        Names of the keys that were set (empty when skipped or already
        loaded). Values are deliberately NOT returned so this result is safe
        to log.

    Skip conditions (all return ``[]`` without touching the environment):
      * running under pytest (keeps the suite hermetic);
      * ``FORGEMIND_SKIP_DOTENV=1``;
      * already loaded in this process;
      * the file does not exist (production images carry no ``.env``).
    """
    global _loaded
    if _loaded:
        return []
    if "pytest" in sys.modules or os.environ.get("FORGEMIND_SKIP_DOTENV") == "1":
        return []
    path = (
        Path(env_file)
        if env_file is not None
        else Path(os.environ.get("FORGEMIND_ENV_FILE") or (REPO_ROOT / ".env"))
    )
    _loaded = True
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        # FileNotFoundError / NotADirectoryError / PermissionError etc.:
        # production containers have no .env — a missing file is not an error.
        return []
    return _parse_and_apply(raw, os.environ)