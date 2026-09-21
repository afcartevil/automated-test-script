#!/usr/bin/env python3
"""
Auto check for SPD feature: 内存压缩.

Rules extracted from provided sheet screenshot:
- 1.0 check:
  1) adb shell dumpsys activity aegean#wbs
  2) cat /proc/memfusion/compress_enable
- 1.1 check:
  1) adb shell dumpsys activity aegean#compact_v2 wbs
  2) cat /proc/memfusion/memcg_compress
- expected:
  - "wbs pass=true" (upper-layer capability)
  - "compress:on"   (lower-layer capability)
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import List, Optional, Tuple


SUPPORTED_V11_KERNELS = {"6.1", "6.12"}
UNSUPPORTED_KERNELS = {"5.15"}
UNKNOWN_KERNELS = {"6.6"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")


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


def run_adb_shell_soft(command: str) -> Tuple[int, str]:
    """Like run_adb_shell but never exits; returns (rc, stdout)."""
    try:
        proc = subprocess.run(
            ["adb", "shell", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    return proc.returncode, proc.stdout or ""


def parse_kernel_mm_from_uname(kernel_release: str) -> Optional[str]:
    match = KERNEL_MM_RE.search(kernel_release)
    if not match:
        return None
    return f"{match.group('major')}.{match.group('minor')}"


def detect_kernel_mm() -> str:
    kernel_release = run_adb_shell("uname -r").strip()
    print("=== kernel version ===")
    print(f"uname -r: {kernel_release}")

    kernel_mm = parse_kernel_mm_from_uname(kernel_release)
    if kernel_mm is None:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- cannot parse kernel major.minor from 'uname -r' output")
        sys.exit(2)

    print(f"parsed kernel: {kernel_mm}")
    return kernel_mm


def select_check_variant(kernel_mm: str) -> Tuple[str, str]:
    if kernel_mm in SUPPORTED_V11_KERNELS:
        return "1.1", "supported"
    if kernel_mm in UNSUPPORTED_KERNELS:
        return "none", "unsupported"
    if kernel_mm in UNKNOWN_KERNELS:
        return "none", "unknown"
    return "none", "unknown"


def check_contains(output: str, token: str) -> bool:
    return token.lower() in output.lower()


def evaluate_mem_compress_v11() -> Tuple[str, List[str], str, str]:
    """
    Run 1.1 table-path checks without printing.
    Returns (status, reasons, dumpsys_out, memcg_out) where status is PASS|FAIL|BLOCKED.
    """
    rc, kernel_release = run_adb_shell_soft("uname -r")
    if rc != 0:
        return "BLOCKED", ["adb shell uname -r failed"], "", ""
    kernel_mm = parse_kernel_mm_from_uname(kernel_release.strip())
    if kernel_mm is None:
        return "BLOCKED", ["cannot parse kernel major.minor from uname -r"], "", ""

    _variant, state = select_check_variant(kernel_mm)
    if state == "unsupported":
        return "BLOCKED", [f"kernel {kernel_mm} not in sheet-supported set for 内存压缩"], "", ""
    if state == "unknown":
        return "BLOCKED", [f"kernel {kernel_mm} support unclear in current sheet; confirm before check"], "", ""

    rc1, dumpsys_out = run_adb_shell_soft("dumpsys activity aegean#compact_v2 wbs")
    rc2, memcg_out = run_adb_shell_soft("cat /proc/memfusion/memcg_compress")
    if rc1 != 0 or rc2 != 0:
        return "BLOCKED", ["failed to read dumpsys or /proc/memfusion/memcg_compress"], dumpsys_out, memcg_out

    has_wbs_pass = check_contains(dumpsys_out, "wbs pass=true")
    has_compress_on = check_contains(memcg_out, "on") or check_contains(memcg_out, "compress:on")
    if has_wbs_pass and has_compress_on:
        return "PASS", [], dumpsys_out, memcg_out
    reasons: List[str] = []
    if not has_wbs_pass:
        reasons.append("missing 'wbs pass=true' in dumpsys aegean#compact_v2 wbs")
    if not has_compress_on:
        reasons.append("memcg_compress does not indicate on")
    return "FAIL", reasons, dumpsys_out, memcg_out


def run_checks_for_v11() -> bool:
    print("=== check variant ===")
    print("using mem compress 1.1 flow")

    st, reasons, dumpsys_out, memcg_out = evaluate_mem_compress_v11()
    if st == "BLOCKED":
        print("\n=== CHECK RESULT: BLOCKED ===")
        for r in reasons:
            print(f"- {r}")
        sys.exit(2)

    print("\n=== dumpsys activity aegean#compact_v2 wbs ===")
    print(dumpsys_out.strip() or "(empty output)")

    print("\n=== cat /proc/memfusion/memcg_compress ===")
    print(memcg_out.strip() or "(empty output)")

    if st == "PASS":
        print("\n=== CHECK RESULT: PASS ===")
        print("- found 'wbs pass=true'")
        print("- found memcg_compress indicates 'on'")
        return True

    print("\n=== CHECK RESULT: FAIL ===")
    for r in reasons:
        print(f"- {r}")
    return False


def main() -> None:
    kernel_mm = detect_kernel_mm()
    variant, state = select_check_variant(kernel_mm)

    if state == "unsupported":
        print("=== CHECK RESULT: BLOCKED ===")
        print(f"- kernel {kernel_mm} is marked as not supported in sheet (内存压缩)")
        sys.exit(2)

    if state == "unknown":
        print("=== CHECK RESULT: BLOCKED ===")
        print(f"- kernel {kernel_mm} support status is not clearly marked in current screenshot")
        print("- please confirm support in sheet before running automated checks")
        sys.exit(2)

    if variant == "1.1":
        ok = run_checks_for_v11()
        sys.exit(0 if ok else 1)

    print("=== CHECK RESULT: BLOCKED ===")
    print("- no executable check variant selected")
    sys.exit(2)


if __name__ == "__main__":
    main()
