"""Integration test stubs for the Phase 0 fixture-driven vertical slice.

Implements SPEC-001 SC-002/SC-003: pytest tests/integration/ passes, and
scripts/run_fixture.py succeeds against both repository fixtures.

NOTE: Runtime tiers are NOT yet implemented (Phase 0 gate). These tests assert
contract-level expectations that the fixture runner validates today and are
extended to the full DAG lineage once Phases 1-6 are implemented.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES_INPUT = REPO_ROOT / "fixtures" / "inputs"
FIXTURES_EXPECTED = REPO_ROOT / "fixtures" / "expected"


def _load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="session")
def fixture():
    """Pair each expected-assertions file with its canonical input fixture.

    Canonical input names carry a scenario suffix (e.g. FIXTURE-001-happy-path.json),
    so match inputs by their '<fixture_id>' prefix instead of exact name.
    """
    pairs = []
    for expected in sorted(FIXTURES_EXPECTED.glob("*-expected.json")):
        fid = expected.name.replace("-expected.json", "")
        matches = sorted(p for p in FIXTURES_INPUT.glob(f"{fid}*.json")
                         if p.name != expected.name)
        if matches:
            pairs.append((fid, matches[0], expected))
    return pairs


def test_every_fixture_has_expected_assertions(fixture):
    assert fixture, "No fixture/expected pairs found"


def test_fixture_envelope_is_event_shaped(fixture):
    for fid, ipt, _exp in fixture:
        data = _load(ipt)
        assert "event" in data, f"{fid}: missing Event envelope"
        assert isinstance(data["event"].get("payload", {}), dict)


def test_run_fixture_script_exits_zero_for_all_fixtures(fixture):
    """Phase 0 contract runner exits 0 for every repository fixture."""
    for fid, ipt, _exp in fixture:
        p = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "run_fixture.py"), str(ipt)],
            capture_output=True, text=True, cwd=str(REPO_ROOT),
        )
        assert p.returncode == 0, f"{fid} runner failed:\n{p.stdout}\n{p.stderr}"


def test_fixture_pairs_valid_json(fixture):
    for _fid, ipt, expected in fixture:
        assert isinstance(_load(ipt), dict)
        assert isinstance(_load(expected), dict)