#!/usr/bin/env python3
"""
Auto check for SPD feature: TOP10 page fault.

Rules extracted from provided sheet screenshot:
- check commands:
  - adb shell dmesg | grep TranMemoryInfo
  - cat /proc/tran_mm_collect/page_fault_sampling
- expected:
  - dmesg has page fault related output
- kernel support:
  - 5.15 / 6.1 / 6.6 / 6.12: supported
"""

from __future__ import annotations

import re
import subprocess
import sys


SUPPORTED_KERNELS = {"5.15", "6.1", "6.6", "6.12"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")
DMESG_KEYWORDS = r"TranMemoryInfo|page.?fault"


def run_adb_shell(command: str, allow_nonzero: bool = False) -> str:
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

    if proc.returncode != 0 and not allow_nonzero:
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

    print("=== CHECK RESULT: BLOCKED ===")
    print(f"- kernel {kernel_mm} support status is unknown")
    print(f"- supported kernels: {', '.join(sorted(SUPPORTED_KERNELS))}")
    sys.exit(2)


def main() -> None:
    detect_kernel_mm()

    dmesg_cmd = f"dmesg | grep -E '{DMESG_KEYWORDS}'"
    dmesg_out = run_adb_shell(dmesg_cmd, allow_nonzero=True)
    sampling_out = run_adb_shell("cat /proc/tran_mm_collect/page_fault_sampling", allow_nonzero=True)

    print("=== dmesg | grep TranMemoryInfo/page fault ===")
    print(dmesg_out.strip() or "(no matched dmesg lines)")

    print("\n=== cat /proc/tran_mm_collect/page_fault_sampling ===")
    print(sampling_out.strip() or "(empty or unreadable output)")

    has_dmesg = bool(dmesg_out.strip())
    has_sampling = bool(sampling_out.strip())
    if has_dmesg and has_sampling:
        print("\n=== CHECK RESULT: PASS ===")
        print("- dmesg has TranMemoryInfo/page fault related output")
        print("- page_fault_sampling node is readable")
        sys.exit(0)

    print("\n=== CHECK RESULT: FAIL ===")
    if not has_dmesg:
        print("- dmesg does not show TranMemoryInfo/page fault related output")
    if not has_sampling:
        print("- /proc/tran_mm_collect/page_fault_sampling has no readable output")
    sys.exit(1)


if __name__ == "__main__":
    main()
