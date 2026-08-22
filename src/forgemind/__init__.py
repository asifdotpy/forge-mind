"""
ForgeMind — Hierarchical Engineering Agent Runtime DAG.

Phase 0 package scaffold: importable so contract/integration tests and the
fixture runner can validate the canonical artifacts against the Spec-Kit
JSON Schema contracts (specs/001-hierarchical-runtime-dag/contracts/).
"""

__version__ = "0.1.0"
__all__ = ["FORGEMIND_SPEC_DIR", "smoke"]

from pathlib import Path

# Canonical repo-wide paths used by both tests and the fixture runner.
REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO_ROOT / "specs" / "001-hierarchical-runtime-dag"
CONTRACTS_DIR = SPEC_DIR / "contracts"
FIXTURES_INPUT_DIR = REPO_ROOT / "fixtures" / "inputs"
FIXTURES_EXPECTED_DIR = REPO_ROOT / "fixtures" / "expected"


def smoke() -> str:
    """Trivial import smoke-check for the Phase 0 scaffold."""
    return "forgemind importable"