#!/usr/bin/env python3
"""Run all SPD CPU feature checks and print a short summary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKS = [
    ("transched", "check_transched.py"),
    ("perf_log", "check_perf_log.py"),
    ("cpu_sched_health", "check_cpu_sched_health.py"),
    ("cgroup_policy", "check_cgroup_policy.py"),
]


def main() -> None:
    results: list[tuple[str, int]] = []
    for name, script in CHECKS:
        path = HERE / script
        print(f"\n{'=' * 60}\n# {name}: {script}\n{'=' * 60}\n")
        proc = subprocess.run([sys.executable, str(path)], check=False)
        results.append((name, proc.returncode))

    print(f"\n{'=' * 60}\n# SUMMARY\n{'=' * 60}")
    for name, code in results:
        label = {0: "PASS", 1: "FAIL", 2: "BLOCKED"}.get(code, f"EXIT_{code}")
        print(f"- {name}: {label} ({code})")

    worst = max(c for _, c in results)
    sys.exit(worst)


if __name__ == "__main__":
    main()
