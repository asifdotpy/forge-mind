"""Runtime boundary contract tests (ADR-009).

ADR-009: ChromaDB provides CONTEXT, not AUTHORITY. It is a development-time
derived index consumed only by SpecForge tooling; no runtime tier may depend
on it and it must be absent from the production image.

These tests make that boundary machine-enforced rather than aspirational.
They use only the standard library plus pytest and MUST pass with chromadb
entirely absent from the environment.
"""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_PACKAGE_DIR = REPO_ROOT / "src" / "forgemind"
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"


def test_no_runtime_module_references_chroma():
    """No *.py under src/forgemind/ may contain any case-insensitive 'chroma'."""
    offenders = []
    for path in sorted(SRC_PACKAGE_DIR.rglob("*.py")):
        if "chroma" in path.read_text(encoding="utf-8").lower():
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert not offenders, (
        f"ADR-009 violation: runtime module(s) reference ChromaDB: {offenders}. "
        "ChromaDB provides CONTEXT, not AUTHORITY — no runtime tier may "
        "read from or write to it."
    )


def test_chromadb_is_not_a_runtime_dependency():
    """[project].dependencies must not declare chromadb (ADR-009)."""
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    offending = [
        dep
        for dep in data["project"]["dependencies"]
        if dep.strip().lower().startswith("chromadb")
    ]
    assert not offending, (
        f"ADR-009 violation: chromadb found in [project].dependencies: "
        f"{offending}. It belongs exclusively in [dependency-groups].dev."
    )


def test_chromadb_remains_declared_in_dev_group():
    """Inverse guard: chromadb must STAY in [dependency-groups].dev (ADR-009).

    Protects against the opposite failure mode — someone 'completing' the
    removal by deleting chromadb everywhere, silently breaking SpecForge's
    Knowledge Brain grounding.
    """
    data = tomllib.loads(PYPROJECT_PATH.read_text(encoding="utf-8"))
    dev_deps = data.get("dependency-groups", {}).get("dev", [])
    assert any(
        dep.strip().lower().startswith("chromadb") for dep in dev_deps
    ), (
        "ADR-009 regression: chromadb missing from [dependency-groups].dev. "
        "SpecForge grounding requires it as a dev dependency."
    )


def test_runtime_imports_succeed_with_chromadb_blocked():
    """The full runtime surface imports with chromadb hard-blocked (ADR-009).

    Implemented as a subprocess so the sys.meta_path blocker cannot leak into
    other tests in this session — a leaked blocker corrupts unrelated tests
    and is very hard to diagnose.
    """
    child_code = r'''
import importlib
import sys


class _ChromaBlocker:
    def find_spec(self, name, path=None, target=None):
        if name == "chromadb" or name.startswith("chromadb."):
            raise ImportError(f"AUDIT-BLOCKED by ADR-009 boundary test: {name}")
        return None


sys.meta_path.insert(0, _ChromaBlocker())

try:
    importlib.import_module("chromadb")
except ImportError:
    pass
else:
    raise SystemExit("internal error: blocker failed to block 'chromadb'")


MODULES = [
    "forgemind",
    "forgemind._paths",
    "forgemind.acquisition",
    "forgemind.supervisor",
    "forgemind.domain_managers",
    "forgemind.workers",
    "forgemind.validator",
    "forgemind.reducer",
    "forgemind.action_gate",
    "forgemind.api",
]

for _name in MODULES:
    importlib.import_module(_name)

print("RUNTIME_IMPORTS_OK")
'''

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT / "src")

    result = subprocess.run(
        [sys.executable, "-c", child_code],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        env=env,
        timeout=120,
    )
    assert result.returncode == 0, (
        "ADR-009 violation: the runtime import surface failed with chromadb "
        f"blocked.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "RUNTIME_IMPORTS_OK" in result.stdout