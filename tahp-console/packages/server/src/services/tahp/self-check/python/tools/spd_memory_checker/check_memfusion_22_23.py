#!/usr/bin/env python3
"""
Auto check for SPD feature: 内存融合 2.2/2.3.

Checks (from Feishu sheet):
1) getprop | grep memfusion
2) getprop | grep swapfile

Expected keys (榫卯 / ro.odm + persist.odm.tr_memfusion):
- ro.odm.tr_memfusion.support = 1
- ro.odm.tr_memfusion.version21.support = true
- ro.odm.tr_memfusion.version22.support = true
- persist.odm.tr_memfusion.swapfile.support = true
- persist.odm.tr_memfusion.swapfile_size_mb: any positive integer (expansion size).
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

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

PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")

# Exact string match (after strip).
EXACT_STRING_KEYS: Dict[str, str] = {
    "ro.odm.tr_memfusion.support": "1",
}

# Case-insensitive "true".
BOOL_TRUE_KEYS = (
    "ro.odm.tr_memfusion.version21.support",
    "ro.odm.tr_memfusion.version22.support",
    "persist.odm.tr_memfusion.swapfile.support",
)

SWAPFILE_SIZE_MB_KEY = "persist.odm.tr_memfusion.swapfile_size_mb"


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


def run_getprop() -> str:
    return run_adb_shell("getprop")


def parse_props(raw: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for line in raw.splitlines():
        match = PROP_LINE_RE.match(line.strip())
        if not match:
            continue
        props[match.group("key")] = match.group("value")
    return props


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

    print(f"kernel support: no ({kernel_mm})")
    print("=== CHECK RESULT: BLOCKED ===")
    print(f"- unsupported kernel version for memfusion 2.2/2.3 check: {kernel_mm}")
    print(f"- supported kernels: {', '.join(sorted(SUPPORTED_KERNELS))}")
    sys.exit(2)


def check_swapfile_size_mb(actual: str | None) -> Tuple[bool, str]:
    if actual is None:
        return False, "(missing)"
    raw = actual.strip()
    try:
        n = int(raw)
    except ValueError:
        return False, f"not int ({actual!r})"
    if n <= 0:
        return False, f"{n} (须 > 0)"
    return True, str(n)


def check_props(props: Dict[str, str]) -> bool:
    rows: List[evr.EvidenceRow] = []

    for key, expected in EXACT_STRING_KEYS.items():
        actual = props.get(key)
        ok = actual is not None and actual.strip() == expected
        rows.append(evr.row(key, expected, actual, ok))

    for key in BOOL_TRUE_KEYS:
        actual = props.get(key)
        ok = actual is not None and actual.strip().lower() == "true"
        rows.append(evr.row(key, "true", actual, ok))

    ok_size, size_detail = check_swapfile_size_mb(props.get(SWAPFILE_SIZE_MB_KEY))
    rows.append(evr.row(SWAPFILE_SIZE_MB_KEY, "正整数 > 0", size_detail, ok_size))

    memfusion_lines = [f"[{k}]: [{v}]" for k, v in sorted(props.items()) if "memfusion" in k]
    swapfile_lines = [f"[{k}]: [{v}]" for k, v in sorted(props.items()) if "swapfile" in k]

    print("=== getprop | grep memfusion ===")
    if memfusion_lines:
        for line in memfusion_lines:
            print(line)
    else:
        print("(no memfusion props found)")

    print("\n=== getprop | grep swapfile ===")
    if swapfile_lines:
        for line in swapfile_lines:
            print(line)
    else:
        print("(no swapfile props found)")

    all_ok = all(r.ok for r in rows)
    evr.print_check_result("PASS" if all_ok else "FAIL", rows)
    return all_ok


def main() -> None:
    detect_kernel_mm()
    raw = run_getprop()
    props = parse_props(raw)
    ok = check_props(props)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
