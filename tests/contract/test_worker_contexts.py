"""Contract tests: deterministic worker contexts (Change 2 + ADR-014 follow-up).

``build_worker_contexts`` must forward ``changed_files`` into every derived
context so workers whose confidence scales with the changeset surface compute
evidence-based values instead of the file-count-free default, and must keep
forwarding ``monitoring_state`` to the monitoring-aware workers (ADR-013).
"""

from forgemind.worker_contexts import build_worker_contexts
from forgemind.workers import WORKER_NAMES_BY_DOMAIN

_ALL_WORKERS = list(WORKER_NAMES_BY_DOMAIN)


def _event():
    return {
        "payload": {
            "changed_files": ["src/app.py", "docs/guide.md"],
            "ci_outcome": "pass",
            "docs_summary": "in-repo documentation updated (1 file(s): docs/guide.md)",
            "alert_signals": [],
            "telemetry_signals": [],
            "monitoring_state": "ok",
            "dependency_scan": [],
        }
    }


def test_changed_files_forwarded_to_every_selected_worker_context():
    contexts = build_worker_contexts(_event(), {"selected_workers": _ALL_WORKERS})
    assert set(contexts) == set(_ALL_WORKERS)
    for ctx in contexts.values():
        assert ctx["inputs"]["changed_files"] == ["src/app.py", "docs/guide.md"]


def test_monitoring_state_still_forwarded_to_monitoring_workers():
    contexts = build_worker_contexts(_event(), {"selected_workers": _ALL_WORKERS})
    for name in ("alert-storm-clustering-worker", "telemetry-correlation-worker"):
        assert contexts[name]["inputs"]["monitoring_state"] == "ok"


def test_changed_files_not_forwarded_without_own_payload_key():
    """Only the worker owning ``changed_files`` sees it when it is the only
    payload key; other workers keep empty inputs (their NO_SIGNAL shards are
    produced from the signal keys, never from changed_files alone)."""
    event = {"payload": {"changed_files": ["src/app.py"]}}
    contexts = build_worker_contexts(event, {"selected_workers": _ALL_WORKERS})
    assert contexts["pr-pre-flight-ast-worker"]["inputs"]["changed_files"] == [
        "src/app.py"
    ]
    for name in (
        "docs-drift-and-spec-worker",
        "build-log-and-flakiness-worker",
        "alert-storm-clustering-worker",
        "telemetry-correlation-worker",
        "security-and-dependency-worker",
    ):
        assert "changed_files" not in contexts[name]["inputs"]


def test_derivation_is_replay_stable():
    plan = {"selected_workers": _ALL_WORKERS}
    assert build_worker_contexts(_event(), plan) == build_worker_contexts(
        _event(), plan
    )
