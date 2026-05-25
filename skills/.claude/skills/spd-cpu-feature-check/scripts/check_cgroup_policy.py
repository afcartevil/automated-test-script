#!/usr/bin/env python3
"""
SPD auto check: cgroup 分组策略.

From spec:
- Before tos16.1:
  1) cat /vendor/etc/task_profiles.json — must contain newly added groups
     (script checks for TRAN_SBG profile names used with settaskprofile)
  2) settaskprofile 1 TRAN_SBG_H_POLICY
     -> "Profile TRAN_SBG_H_POLICY is applied successfully!"
- tos16.1 and later:
  getprop ro.tr_perf.aegean.cg.kernel.support -> 1

Optional env SPD_TOS_VERSION="16.0" overrides auto-detect (major.minor).
TOS auto-detect: env, then ro.transsion.tos.version / …, then getprop|grep version (tos_detect).
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

_skills = Path(__file__).resolve().parents[2]
_shared = _skills / "spd-shared" / "scripts"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))
import tos_detect  # noqa: E402

SUPPORTED_KERNELS = {"5.15", "6.1", "6.6", "6.12"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")

# Minimum signal for "new groups" in task_profiles.json (sheet references TRAN_SBG_H_POLICY)
JSON_MARKERS = (
    "TRAN_SBG_H_POLICY",
    "TRAN_SBG",
)

SETTASK_SUCCESS = "Profile TRAN_SBG_H_POLICY is applied successfully!"

PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")


def run_adb_shell(command: str) -> tuple[int, str]:
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
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_props(raw: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in raw.splitlines():
        m = PROP_LINE_RE.match(line.strip())
        if m:
            props[m.group("key")] = m.group("value")
    return props


def is_before_tos_16_1(mm: tuple[int, int] | None) -> bool:
    """True -> legacy task_profiles + settaskprofile path."""
    if mm is None:
        # Unknown: prefer new prop path first (safer on modern devices)
        return False
    maj, mino = mm
    if maj < 16:
        return True
    if maj == 16 and mino < 1:
        return True
    return False


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


def check_legacy_path() -> bool:
    code, raw = run_adb_shell("cat /vendor/etc/task_profiles.json")
    print("=== cat /vendor/etc/task_profiles.json (markers) ===")
    if code != 0 or not raw.strip():
        print(raw.strip() or "(empty)")
        return False

    found = [mk for mk in JSON_MARKERS if mk in raw]
    for mk in found:
        print(f"- found substring: {mk}")

    if not found:
        print("(no TRAN_SBG markers in file)")
        return False

    # Optional: valid JSON
    try:
        json.loads(raw)
        print("- JSON parse: OK")
    except json.JSONDecodeError as e:
        print(f"- JSON parse: FAIL ({e})")
        return False

    code2, out2 = run_adb_shell("settaskprofile 1 TRAN_SBG_H_POLICY")
    print("\n=== settaskprofile 1 TRAN_SBG_H_POLICY ===")
    print(out2.strip())
    if SETTASK_SUCCESS in out2:
        return True
    return False


def check_modern_path(props: dict[str, str]) -> bool:
    val = props.get("ro.tr_perf.aegean.cg.kernel.support", "").strip()
    print("=== getprop ro.tr_perf.aegean.cg.kernel.support ===")
    print(val or "(empty)")
    return val == "1"


def main() -> None:
    detect_kernel_mm()

    code, raw = run_adb_shell("getprop")
    if code != 0:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- getprop failed")
        sys.exit(2)
    props = parse_props(raw)

    _gc, gv = run_adb_shell("sh -c \"getprop | grep version\"")
    print("=== getprop | grep version (TOS / 版本截取参考) ===")
    print((gv.strip() or "(empty)")[:8000])
    tos_mm, tos_src = tos_detect.detect_tos_mm_combined(props, gv)
    if tos_mm is not None:
        print(f"=== TOS parsed (source: {tos_src}) -> {tos_mm[0]}.{tos_mm[1]} ===")

    legacy = is_before_tos_16_1(tos_mm)

    if tos_mm is None:
        print("=== TOS branch ===\nversion unknown (SPD_TOS_VERSION / TOS props / getprop|grep version); try modern prop first, then legacy")
        if check_modern_path(props):
            print("\n=== CHECK RESULT: PASS ===")
            sys.exit(0)
        if check_legacy_path():
            print("\n=== CHECK RESULT: PASS ===")
            sys.exit(0)
        print("\n=== CHECK RESULT: FAIL ===")
        print("- neither modern aegean prop nor legacy task_profiles/settaskprofile passed")
        sys.exit(1)

    if legacy:
        ok = check_legacy_path()
    else:
        ok = check_modern_path(props)

    if ok:
        print("\n=== CHECK RESULT: PASS ===")
        sys.exit(0)
    print("\n=== CHECK RESULT: FAIL ===")
    sys.exit(1)


if __name__ == "__main__":
    main()
