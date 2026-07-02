#!/usr/bin/env python3
"""
Auto check for SPD feature: look around.

Kernel branches:
- 6.1: native kernel LRU_GEN (look around); check /sys/kernel/mm/lru_gen/enabled
- 5.15 / 6.6: Tran look_around.ko module; check /sys/module/look_around/
- 6.12: not supported (BLOCKED)
"""

from __future__ import annotations

import re
import subprocess
import sys
from typing import Set, Tuple


SUPPORTED_KERNELS = {"5.15", "6.1", "6.6"}
UNSUPPORTED_KERNELS = {"6.12"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")

# Tran module path (5.15 / 6.6)
EXPECTED_MODULE_ITEMS = {
    "coresize",
    "holders",
    "initsize",
    "initstate",
    "notes",
    "refcnt",
    "sections",
    "taint",
    "uevent",
}

# Native LRU_GEN path (6.1)
LRU_GEN_ENABLED_PATH = "/sys/kernel/mm/lru_gen/enabled"


def run_adb_shell(command: str, *, allow_nonzero: bool = False) -> Tuple[str, int]:
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

    return proc.stdout, proc.returncode


def detect_kernel_mm() -> str:
    kernel_release, _ = run_adb_shell("uname -r")
    kernel_release = kernel_release.strip()
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
        print(f"- kernel {kernel_mm} is marked as not supported for look around")
        sys.exit(2)

    print("=== CHECK RESULT: BLOCKED ===")
    print(f"- kernel {kernel_mm} support status is unknown")
    print(f"- supported kernels: {', '.join(sorted(SUPPORTED_KERNELS))}")
    print(f"- unsupported kernels: {', '.join(sorted(UNSUPPORTED_KERNELS))}")
    sys.exit(2)


def parse_items(raw: str) -> Set[str]:
    return {x.strip() for x in raw.split() if x.strip()}


def parse_lru_gen_enabled(raw: str) -> int | None:
    text = raw.strip()
    if not text:
        return None
    try:
        return int(text, 0)
    except ValueError:
        return None


def check_native_lru_gen() -> None:
    print("=== check branch: kernel 6.1 native LRU_GEN ===")
    print(f"command: cat {LRU_GEN_ENABLED_PATH}")

    raw, rc = run_adb_shell(f"cat {LRU_GEN_ENABLED_PATH}", allow_nonzero=True)
    print("=== cat /sys/kernel/mm/lru_gen/enabled ===")
    print(raw.strip() or "(empty output)")

    if rc != 0 or not raw.strip():
        print("\n=== CHECK RESULT: FAIL ===")
        print(f"- {LRU_GEN_ENABLED_PATH} is missing or unreadable")
        sys.exit(1)

    value = parse_lru_gen_enabled(raw)
    if value is None:
        print("\n=== CHECK RESULT: FAIL ===")
        print("- cannot parse lru_gen enabled value")
        sys.exit(1)

    if value == 0:
        print("\n=== CHECK RESULT: FAIL ===")
        print("- lru_gen enabled value is 0 (look around not active)")
        sys.exit(1)

    print("\n=== CHECK RESULT: PASS ===")
    print(f"- native LRU_GEN enabled (value={raw.strip()})")
    sys.exit(0)


def check_module_look_around(kernel_mm: str) -> None:
    print(f"=== check branch: kernel {kernel_mm} Tran look_around module ===")
    print("command: ls /sys/module/look_around/")

    raw, rc = run_adb_shell("ls /sys/module/look_around/", allow_nonzero=True)
    print("=== ls /sys/module/look_around/ ===")
    print(raw.strip() or "(empty output)")

    if rc != 0 or not raw.strip():
        print("\n=== CHECK RESULT: FAIL ===")
        print("- /sys/module/look_around/ is missing or unreadable")
        sys.exit(1)

    got = parse_items(raw)
    missing = sorted(EXPECTED_MODULE_ITEMS - got)

    if not missing:
        print("\n=== CHECK RESULT: PASS ===")
        print("- all expected directory items are present")
        sys.exit(0)

    print("\n=== CHECK RESULT: FAIL ===")
    print("- missing expected items:")
    for item in missing:
        print(f"  - {item}")
    sys.exit(1)


def main() -> None:
    kernel_mm = detect_kernel_mm()
    if kernel_mm == "6.1":
        check_native_lru_gen()
    else:
        check_module_look_around(kernel_mm)


if __name__ == "__main__":
    main()
