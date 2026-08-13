#!/usr/bin/env python3
"""
SPD auto check: 性能统计 perf log.

Rule: `dmesg | grep '[K]'` produces at least one non-empty line -> PASS.
"""

from __future__ import annotations

import re
import subprocess
import sys
import time

SUPPORTED_KERNELS = {"5.15", "6.1", "6.6", "6.12"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")

# First attempt; on each failure wait RETRY_SLEEP_SEC then repeat, up to RETRIES_AFTER_FAIL extra tries
# (1 + 3 = 4 dmesg checks total).
RETRIES_AFTER_FAIL = 3
RETRY_SLEEP_SEC = 1.0


def run_adb_shell(command: str) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["adb", "shell", command],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: adb not found in PATH.", file=sys.stderr)
        sys.exit(2)
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, out


def detect_kernel_mm() -> str:
    code, out = run_adb_shell("uname -r")
    if code != 0:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- failed to read kernel version")
        sys.exit(2)
    kr = out.strip()
    print("=== kernel version ===")
    print(f"uname -r: {kr}")
    m = KERNEL_MM_RE.search(kr)
    if not m:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- cannot parse kernel major.minor")
        sys.exit(2)
    mm = f"{m.group('major')}.{m.group('minor')}"
    if mm not in SUPPORTED_KERNELS:
        print("=== CHECK RESULT: BLOCKED ===")
        print(f"- kernel {mm} not in supported list: {sorted(SUPPORTED_KERNELS)}")
        sys.exit(2)
    print(f"kernel support (sheet): yes ({mm})")
    return mm


def run_perf_log_check_once(attempt: int, total_attempts: int) -> tuple[bool, int, str]:
    """
    dmesg | grep '[K]'; PASS if any non-empty line in stdout+stderr.
    Returns (passed, adb_return_code, combined_output).
    """
    # Bracket grep trick: [K] matches literal K in grep
    code, combined = run_adb_shell("dmesg | grep '[K]'")
    print(f"=== dmesg | grep \"[K]\" (attempt {attempt}/{total_attempts}) ===")
    lines = [ln for ln in combined.splitlines() if ln.strip()]
    show = lines[:80]
    for ln in show:
        print(ln)
    if len(lines) > 80:
        print(f"... ({len(lines)} lines total, truncated)")

    if lines:
        print("\n=== CHECK RESULT: PASS ===")
        print("- dmesg | grep '[K]' has non-empty output")
        return True, code, combined

    return False, code, combined


def main() -> None:
    detect_kernel_mm()

    total_attempts = 1 + RETRIES_AFTER_FAIL
    last_code = 0
    for attempt in range(1, total_attempts + 1):
        passed, code, _combined = run_perf_log_check_once(attempt, total_attempts)
        last_code = code
        if passed:
            sys.exit(0)
        if attempt < total_attempts:
            print(
                f"\n--- no grep output, retry in {RETRY_SLEEP_SEC}s "
                f"({attempt}/{total_attempts} done) ---\n"
            )
            time.sleep(RETRY_SLEEP_SEC)

    print("\n=== CHECK RESULT: FAIL ===")
    print(
        "- dmesg | grep '[K]' produced no non-empty lines "
        f"after {total_attempts} attempt(s)"
    )
    if last_code != 0:
        print(f"- adb shell exit code: {last_code} (dmesg may be restricted without root)")
    sys.exit(1)


if __name__ == "__main__":
    main()
