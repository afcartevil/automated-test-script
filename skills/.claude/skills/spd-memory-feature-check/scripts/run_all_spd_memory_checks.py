#!/usr/bin/env python3
"""Run all SPD memory feature checks and print a short summary."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# 顺序：先版本识别，再按依赖关系执行各项
CHECKS = [
    ("memfusion_compress_version", "detect_memfusion_compress_version.py", ["--json"]),
    ("mem_compress_status", "check_mem_compress_status.py", []),
    ("memfusion_22_23", "check_memfusion_22_23.py", []),
    ("kswapd_bind", "check_kswapd_bind.py", []),
    ("shrink_slab", "check_shrink_slab.py", []),
    ("look_around", "check_look_around.py", []),
    ("kswapd_reclaim_log", "check_kswapd_reclaim_log.py", []),
    ("top10_page_fault", "check_top10_page_fault.py", []),
    ("quantus_framework", "check_quantus_framework.py", []),
    ("memory_allocate", "check_memory_allocate.py", []),
]


def main() -> None:
    results: list[tuple[str, int]] = []
    for name, script, extra_args in CHECKS:
        path = HERE / script
        if not path.exists():
            print(f"skip missing script: {script}")
            continue
        print(f"\n{'=' * 60}\n# {name}: {script}\n{'=' * 60}\n")
        proc = subprocess.run(
            [sys.executable, str(path), *extra_args],
            check=False,
        )
        results.append((name, proc.returncode))

    if not results:
        print("SKILL_FAILED: 未找到任何可执行的内存检查脚本")
        sys.exit(1)

    print(f"\n{'=' * 60}\n# SUMMARY\n{'=' * 60}")
    for name, code in results:
        label = {0: "PASS", 1: "FAIL", 2: "BLOCKED"}.get(code, f"EXIT_{code}")
        print(f"- {name}: {label} ({code})")

    worst = max(c for _, c in results)
    sys.exit(worst)


if __name__ == "__main__":
    main()
