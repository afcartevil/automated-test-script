#!/usr/bin/env python3
"""
Auto check for SPD feature: kswapd绑中小核.

Rules extracted from provided sheet screenshot:
- check command: getprop | grep kswapd0
- expected key: persist.odm.tr_powerhal.kswapd0_bind.feature.support
- expected value: 1 or -1
- kernel support:
  - 5.15: unsupported
  - 6.1 / 6.6 / 6.12: supported
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict

_here = Path(__file__).resolve().parent
for _shared in (
    _here.parent / "spd_shared" / "scripts",
    _here.parents[2] / "spd-shared" / "scripts",
):
    if _shared.is_dir() and str(_shared) not in sys.path:
        sys.path.insert(0, str(_shared))
import evidence_report as evr  # noqa: E402

SUPPORTED_KERNELS = {"6.1", "6.6", "6.12"}
UNSUPPORTED_KERNELS = {"5.15"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")
PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")

# Use latest sheet key as primary; keep old keys as compatibility fallback.
EXPECTED_KEYS = (
    "persist.odm.tr_powerhal.kswapd0_bind.feature.support",
    "persist.vendor.powerhal.kswapd0_bind_enable",
    "persist.odm.powerhal.kswapd0_bind_enable",
)
EXPECTED_VALUES = {"1", "-1"}


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
        print(f"- kernel {kernel_mm} is marked as not supported for kswapd bind")
        sys.exit(2)

    print("=== CHECK RESULT: BLOCKED ===")
    print(f"- kernel {kernel_mm} support status is unknown")
    print(f"- supported kernels: {', '.join(sorted(SUPPORTED_KERNELS))}")
    print(f"- unsupported kernels: {', '.join(sorted(UNSUPPORTED_KERNELS))}")
    sys.exit(2)


def parse_props(raw_getprop: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for line in raw_getprop.splitlines():
        line = line.strip()
        match = PROP_LINE_RE.match(line)
        if match:
            props[match.group("key")] = match.group("value")
    return props


def main() -> None:
    detect_kernel_mm()
    raw_getprop = run_adb_shell("getprop")
    props = parse_props(raw_getprop)

    print("=== getprop | grep kswapd0 ===")
    kswapd_lines = [f"[{k}]: [{v}]" for k, v in props.items() if "kswapd0" in k]
    if kswapd_lines:
        for line in kswapd_lines:
            print(line)
    else:
        print("(no kswapd0 related props found)")

    found_key = None
    found_value = None
    for key in EXPECTED_KEYS:
        if key in props:
            found_key = key
            found_value = props[key]
            break

    if found_key is None:
        rows = [
            evr.row(
                "kswapd0_bind 属性",
                "存在以下任一键且值为 1 或 -1: " + " / ".join(EXPECTED_KEYS),
                "(missing)",
                False,
            )
        ]
        evr.print_check_result("FAIL", rows)
        sys.exit(1)

    ok = found_value in EXPECTED_VALUES
    rows = [evr.row(found_key, "1 或 -1", found_value, ok)]
    evr.print_check_result("PASS" if ok else "FAIL", rows)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
