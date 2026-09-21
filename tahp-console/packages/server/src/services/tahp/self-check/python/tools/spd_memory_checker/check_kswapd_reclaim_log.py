#!/usr/bin/env python3
"""
Auto check for SPD feature: kswapd回收效率log.

Rules extracted from provided sheet screenshot:
- check command:
  - adb shell logcat | grep TranMemoryInfo (or TranMemon/Info in sheet text)
  - or adb shell dmesg | grep TranMemoryInfo
- expected:
  - related log output exists
- kernel support:
  - 5.15 / 6.1 / 6.6 / 6.12: supported
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
for _shared in (
    _here.parent / "spd_shared" / "scripts",
    _here.parents[2] / "spd-shared" / "scripts",
):
    if _shared.is_dir() and str(_shared) not in sys.path:
        sys.path.insert(0, str(_shared))
import evidence_report as evr  # noqa: E402

SUPPORTED_KERNELS = {"5.15", "6.1", "6.6", "6.12"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")

# Tolerate possible naming drift from screenshot text.
KEYWORD_PATTERN = r"TranMemoryInfo|TranMemon[/_]?Info"


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

    # keep stdout only for grep pipeline checks; stderr is not feature evidence
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

    logcat_cmd = f"logcat -d | grep -E '{KEYWORD_PATTERN}'"
    dmesg_cmd = f"dmesg | grep -E '{KEYWORD_PATTERN}'"

    # grep returns non-zero if no match; treat as non-fatal and parse output.
    logcat_out = run_adb_shell(logcat_cmd, allow_nonzero=True)
    dmesg_out = run_adb_shell(dmesg_cmd, allow_nonzero=True)

    print("=== logcat -d | grep TranMemoryInfo ===")
    print(logcat_out.strip() or "(no matched logcat lines)")

    print("\n=== dmesg | grep TranMemoryInfo ===")
    print(dmesg_out.strip() or "(no matched dmesg lines)")

    has_logcat = bool(logcat_out.strip())
    has_dmesg = bool(dmesg_out.strip())
    ok = has_logcat or has_dmesg
    sample = "(empty)"
    if has_logcat:
        sample = "logcat: " + logcat_out.strip().splitlines()[0][:100]
    elif has_dmesg:
        sample = "dmesg: " + dmesg_out.strip().splitlines()[0][:100]

    rows = [
        evr.row(
            "TranMemoryInfo 日志",
            "logcat 或 dmesg 至少一路命中",
            sample,
            ok,
        )
    ]
    extra = None if ok else ["sheet note: 可等待片刻并操作 App 后重测"]
    evr.print_check_result("PASS" if ok else "FAIL", rows, extra_lines=extra)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
