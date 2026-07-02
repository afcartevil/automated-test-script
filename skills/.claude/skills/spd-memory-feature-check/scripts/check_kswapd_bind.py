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
from typing import Dict


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
        print("\n=== CHECK RESULT: FAIL ===")
        print("- expected key not found:")
        for key in EXPECTED_KEYS:
            print(f"  - {key}")
        sys.exit(1)

    if found_value in EXPECTED_VALUES:
        print("\n=== CHECK RESULT: PASS ===")
        print(f"- {found_key} = {found_value}")
        print("- value is in expected set: {1, -1}")
        sys.exit(0)

    print("\n=== CHECK RESULT: FAIL ===")
    print(f"- {found_key}: expected one of {sorted(EXPECTED_VALUES)}, actual '{found_value}'")
    sys.exit(1)


if __name__ == "__main__":
    main()
