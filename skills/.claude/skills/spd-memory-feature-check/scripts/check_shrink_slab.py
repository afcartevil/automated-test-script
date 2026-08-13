#!/usr/bin/env python3
"""
Auto check for SPD feature: shrink_slab.

Rules extracted from provided sheet screenshot:
- check command: 检查shrink_slab: ps-ef | grep shrink_slab
- expected output includes: [kshrink_slabd]
- kernel support:
  - 5.15 / 6.1 / 6.6: supported
  - 6.12: unsupported
"""

from __future__ import annotations

import re
import subprocess
import sys


SUPPORTED_KERNELS = {"5.15", "6.1", "6.6"}
UNSUPPORTED_KERNELS = {"6.12"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")
EXPECTED_TOKEN = "kshrink_slabd"


def run_adb_shell(command: str) -> str:
    try:
        proc = subprocess.run(
            ["adb", "shell", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: adb not found in PATH.", file=sys.stderr)
        sys.exit(2)

    if proc.returncode != 0:
        print(f"ERROR: failed to run 'adb shell {command}'.", file=sys.stderr)
        if proc.stderr:
            print(proc.stderr.strip(), file=sys.stderr)
        sys.exit(2)

    return proc.stdout


def detect_kernel_mm() -> str:
    kernel_release = run_adb_shell("uname -r").strip()
    print("=== kernel version ===")
    print(f"uname -r: {kernel_release}")

    match = KERNEL_MM_RE.search(kernel_release)
    if not match:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- cannot parse kernel major.minor from 'uname -r' output")
        sys.exit(2)

    kernel_mm = f"{match.group('major')}.{match.group('minor')}"
    print(f"parsed kernel: {kernel_mm}")

    if kernel_mm in SUPPORTED_KERNELS:
        print(f"kernel support: yes ({kernel_mm})")
        return kernel_mm
    if kernel_mm in UNSUPPORTED_KERNELS:
        print(f"kernel support: no ({kernel_mm})")
        print("=== CHECK RESULT: BLOCKED ===")
        print(f"- kernel {kernel_mm} is marked as not supported for shrink_slab")
        sys.exit(2)

    print("=== CHECK RESULT: BLOCKED ===")
    print(f"- kernel {kernel_mm} support status is unknown")
    print(f"- supported kernels: {', '.join(sorted(SUPPORTED_KERNELS))}")
    print(f"- unsupported kernels: {', '.join(sorted(UNSUPPORTED_KERNELS))}")
    sys.exit(2)


def main() -> None:
    detect_kernel_mm()

    ps_out = run_adb_shell("ps -ef | grep shrink_slab")
    print("=== ps -ef | grep shrink_slab ===")
    print(ps_out.strip() or "(empty output)")

    if EXPECTED_TOKEN in ps_out:
        print("\n=== CHECK RESULT: PASS ===")
        print(f"- found expected token: [{EXPECTED_TOKEN}]")
        sys.exit(0)

    print("\n=== CHECK RESULT: FAIL ===")
    print(f"- missing expected token: [{EXPECTED_TOKEN}]")
    sys.exit(1)


if __name__ == "__main__":
    main()
