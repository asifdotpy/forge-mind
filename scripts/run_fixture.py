#!/usr/bin/env python3
"""
ForgeMind Phase 0 Fixture Runner.

Validates canonical Event-envelope fixtures against the machine-readable JSON
Schema contracts in specs/001-hierarchical-runtime-dag/contracts/.

Phase 0 scope: only the Event envelope exists as a runtime artifact. Downstream
artifacts (CoveragePlan ... Escalation) are not implemented yet; the runner
therefore (a) validates the Event envelope against event.schema.json, and
(b) cross-checks that every artifact listed in fixture.expected_artifacts is
covered by a group in the matching fixtures/expected/*-expected.json file.

Usage:
    python scripts/run_fixture.py                                            # all fixtures
    python scripts/run_fixture.py fixtures/inputs/FIXTURE-001-happy-path.json
"""

import argparse
import json
import sys
from pathlib import Path

# Bootstrap: allow running as a standalone script with a src/ layout package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    import jsonschema
except ImportError:
    sys.exit("Error: 'jsonschema' is required. Install with: uv sync")

from forgemind import CONTRACTS_DIR, FIXTURES_EXPECTED_DIR, FIXTURES_INPUT_DIR


def load_json(path):
    with Path(path).open(encoding="utf-8") as f:
        return json.load(f)


def validate_fixture(fixture_path: Path) -> int:
    """Validate one fixture. Returns the number of errors found."""
    fixture = load_json(fixture_path)
    fid = fixture.get("fixture_id", fixture_path.stem)
    errors = 0

    # 1) Event envelope must validate against the event contract.
    event_schema = CONTRACTS_DIR / "event.schema.json"
    try:
        jsonschema.validate(fixture.get("event", {}), load_json(event_schema))
        print(f"[ok] {fid}: event envelope passes event.schema.json")
    except jsonschema.ValidationError as exc:
        print(f"[FAIL] {fid}: event envelope vs event.schema.json -> {exc.message}")
        return 1

    # 2) Expected assertions must exist for this fixture.
    expected_file = FIXTURES_EXPECTED_DIR / f"{fid}-expected.json"
    if not expected_file.exists():
        print(f"[FAIL] {fid}: missing expected assertions file {expected_file.name}")
        return 1
    expected = load_json(expected_file)
    groups = {g.get("artifact") for g in expected.get("assertions", [])}
    print(f"[ok] {fid}: expected assertions present ({len(groups)} groups)")

    # 3) Cross-check: every artifact the fixture declares must be covered by an assertion group.
    for artifact in fixture.get("expected_artifacts", []):
        if artifact in groups:
            print(f"[ok] {fid}: artifact '{artifact}' covered by assertions")
        else:
            print(f"[FAIL] {fid}: expected artifact '{artifact}' not covered by assertions")
            errors += 1

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="ForgeMind Phase 0 fixture runner")
    parser.add_argument("fixture", type=Path, nargs="?",
                        help="Path to a fixture JSON under fixtures/inputs/")
    args = parser.parse_args()

    if args.fixture is not None:
        if not args.fixture.exists():
            sys.exit(f"Error: fixture not found: {args.fixture}")
        total = validate_fixture(args.fixture)
    else:
        fixture_files = sorted(FIXTURES_INPUT_DIR.glob("*.json"))
        if not fixture_files:
            sys.exit("Error: no fixtures found in fixtures/inputs/")
        total = sum(validate_fixture(p) for p in fixture_files)

    print(f"\nFixture validation complete. {total} error(s).")
    return 0 if total == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())


if __name__ == "__main__":
    raise SystemExit(main())