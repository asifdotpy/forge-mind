#!/usr/bin/env python3
"""
Latency benchmark: deterministic vs adk+runner modes.

Times N runs of each mode on FIXTURE-007 and reports mean/p50/p95/p99
in a comparison table.

Usage:
    PYTHONPATH=src python scripts/benchmark_latency.py
    PYTHONPATH=src python scripts/benchmark_latency.py --runs 5 --timeout 30
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

FIXTURE_PATH = (
    REPO_ROOT / "fixtures" / "inputs" / "FIXTURE-007-m3-judge-surface-action.json"
)


def load_fixture() -> dict:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def percentile(data: list[float], p: float) -> float:
    """Linear-interpolation percentile (numpy-style)."""
    s = sorted(data)
    k = (len(s) - 1) * (p / 100)
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (k - f) * (s[c] - s[f])


def _run_deterministic(body, n: int, timeout: float | None):
    """Run the pure-Python deterministic pipeline N times."""
    from forgemind.api.pipeline import run_pipeline

    times: list[float] = []
    timeouts = 0
    for i in range(n):
        start = time.perf_counter()
        try:
            result = run_pipeline(body)
            elapsed = time.perf_counter() - start
            if timeout and elapsed > timeout:
                timeouts += 1
                print(f"  deterministic  {i+1:>2}/{n}: {elapsed*1000:8.2f} ms  [TIMEOUT]", file=sys.stderr)
            else:
                print(f"  deterministic  {i+1:>2}/{n}: {elapsed*1000:8.2f} ms", file=sys.stderr)
                times.append(elapsed)
        except Exception as exc:
            elapsed = time.perf_counter() - start
            print(f"  deterministic  {i+1:>2}/{n}: {elapsed*1000:8.2f} ms  [ERROR: {exc}]", file=sys.stderr)
    return times, timeouts


def _run_adk_runner(body, n: int, timeout: float | None):
    """Run the ADK 2.0 Runner pipeline N times."""
    from forgemind.adk_runtime import run_adk_runner_pipeline

    times: list[float] = []
    results: list = []
    timeouts = 0
    for i in range(n):
        start = time.perf_counter()
        try:
            result = run_adk_runner_pipeline(body)
            elapsed = time.perf_counter() - start
            if timeout and elapsed > timeout:
                timeouts += 1
                print(f"  adk+runner     {i+1:>2}/{n}: {elapsed*1000:8.2f} ms  [TIMEOUT]", file=sys.stderr)
            else:
                tag = "ok" if result is not None else "fallback"
                print(f"  adk+runner     {i+1:>2}/{n}: {elapsed*1000:8.2f} ms  [{tag}]", file=sys.stderr)
                times.append(elapsed)
            results.append(result)
        except Exception as exc:
            elapsed = time.perf_counter() - start
            print(f"  adk+runner     {i+1:>2}/{n}: {elapsed*1000:8.2f} ms  [ERROR: {exc}]", file=sys.stderr)
            results.append(None)
    return times, results, timeouts


def _stats(times: list[float]) -> dict:
    if not times:
        return {"mean": float("nan"), "p50": float("nan"), "p95": float("nan"), "p99": float("nan")}
    return {
        "mean": statistics.mean(times),
        "p50": percentile(times, 50),
        "p95": percentile(times, 95),
        "p99": percentile(times, 99),
    }


def _fmt(seconds: float) -> str:
    if isinstance(seconds, float) and (seconds != seconds):  # NaN check
        return "     n/a"
    return f"{seconds * 1000:>8.2f} ms"


def _print_table(det: dict, run: dict, det_to: int, run_to: int, fallbacks: int, n: int) -> None:
    print()
    print("=" * 64)
    print("  Latency Benchmark  |  deterministic vs adk+runner")
    print(f"  Runs per mode: {n}   |   Fixture: FIXTURE-007")
    print("=" * 64)
    print()
    print(f"{'Metric':<10} {'Deterministic':>14} {'ADK+Runner':>14} {'Δ overhead':>12}")
    print("-" * 50)

    for label, key in [("mean", "mean"), ("p50", "p50"), ("p95", "p95"), ("p99", "p99")]:
        d, r = det[key], run[key]
        if isinstance(d, float) and d != d:
            overhead = "n/a"
        elif isinstance(r, float) and r != r:
            overhead = "n/a"
        elif d > 0:
            overhead = f"{((r - d) / d * 100):>10.1f}%"
        else:
            overhead = "inf"
        print(f"{label:<10} {_fmt(d):>14} {_fmt(r):>14} {overhead:>12}")

    print()
    print(f"  Deterministic timeouts : {det_to}/{n}")
    print(f"  ADK+Runner timeouts    : {run_to}/{n}")
    print(f"  ADK+Runner fallbacks   : {fallbacks}/{n}")
    print(f"  GOOGLE_API_KEY set     : {'yes' if os.environ.get('GOOGLE_API_KEY') else 'no'}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Latency benchmark: deterministic vs adk+runner")
    parser.add_argument("--runs", type=int, default=10, help="Number of runs per mode (default: 10)")
    parser.add_argument("--timeout", type=float, default=None, help="Per-run timeout in seconds (default: none)")
    args = parser.parse_args()

    n = args.runs
    timeout = args.timeout

    fixture = load_fixture()

    from forgemind.api.models import EventInput

    body = EventInput(**fixture)

    print(f"Running {n} iterations per mode …\n", file=sys.stderr)

    print("[1/2] deterministic", file=sys.stderr)
    det_times, det_to = _run_deterministic(body, n, timeout)

    print("\n[2/2] adk+runner", file=sys.stderr)
    run_times, run_results, run_to = _run_adk_runner(body, n, timeout)

    det_s = _stats(det_times)
    run_s = _stats(run_times)
    fallbacks = sum(1 for r in run_results if r is None)

    _print_table(det_s, run_s, det_to, run_to, fallbacks, n)


if __name__ == "__main__":
    main()