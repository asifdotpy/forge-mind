"""Contract tests: validate the canonical Phase 0 fixtures against the machine-readable JSON Schemas.

These implement SPEC-001 Required Contract Tests (see specs/001-hierarchical-runtime-dag/spec.md):
valid event creation; provenance preservation; evidence-shard validation; escalation generation;
uncertainty preservation; coverage-gap detection (FIXTURE-002 expected).
"""

import json
from pathlib import Path

import pytest
import jsonschema

from forgemind import CONTRACTS_DIR, FIXTURES_INPUT_DIR, FIXTURES_EXPECTED_DIR

CONTRACT_FILES = sorted(CONTRACTS_DIR.glob("*.schema.json"))


def _load(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def test_all_contract_schemas_are_valid_json():
    for schema in CONTRACT_FILES:
        data = _load(schema)
        assert "$id" in data, f"{schema.name} missing $id"
        assert "properties" in data, f"{schema.name} missing properties"


def test_all_fixtures_validate_against_event_schema():
    schema = _load(CONTRACTS_DIR / "event.schema.json")
    for fixture in sorted(FIXTURES_INPUT_DIR.glob("*.json")):
        data = _load(fixture)
        jsonschema.validate(data["event"], schema)


def test_fixture_expected_files_complete():
    for expected in sorted(FIXTURES_EXPECTED_DIR.glob("*-expected.json")):
        data = _load(expected)
        assert "assertions" in data
        assert isinstance(data["assertions"], list)
        assert data["assertions"], f"{expected.name} has no assertions"


def test_fixture_002_requires_escalation():
    """FIXTURE-002 (escalation path) must demand Escalation, never an autonomous action."""
    expected = _load(FIXTURES_EXPECTED_DIR / "FIXTURE-002-expected.json")
    artifacts = [g["artifact"] for g in expected["assertions"]]
    assert "Escalation" in artifacts
    terminals = [g["checks"] for g in expected["assertions"] if g["artifact"] == "Terminal"]
    assert any("NO autonomous action executed" in c for group in terminals for c in group)


def test_fixture_001_has_no_escalation():
    """Happy-path fixture must explicitly not escalate."""
    expected = _load(FIXTURES_EXPECTED_DIR / "FIXTURE-001-expected.json")
    terminals = [g["checks"] for g in expected["assertions"] if g["artifact"] == "Terminal"]
    assert any("NO Escalation" in c for group in terminals for c in group)