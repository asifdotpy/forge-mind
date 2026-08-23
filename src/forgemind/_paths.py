"""Canonical repository paths for ForgeMind (single source of truth).

Imported by :mod:`forgemind` (which re-exports them for backwards
compatibility) and by submodules that need contract locations without
circular imports.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPEC_DIR = REPO_ROOT / "specs" / "001-hierarchical-runtime-dag"
CONTRACTS_DIR = SPEC_DIR / "contracts"
FIXTURES_INPUT_DIR = REPO_ROOT / "fixtures" / "inputs"
FIXTURES_EXPECTED_DIR = REPO_ROOT / "fixtures" / "expected"
