#!/usr/bin/env python3
"""
Auto check for SPD feature: 内存分配.

Support gate (SPD / 业务约定：仅 **TOS16.3 及以上** 且 **Linux kernel 6.0 及以上** 才做内存分配自动检查):
- Linux kernel: parsed (major, minor) must be **>= (6, 0)**（kernel6 及以上，含 6.0.x；**5.15** 等 **BLOCKED**）。
- TOS: parsed (major, minor) must be **>= (16, 3)**（**TOS16.3** 起；**16.2 及以下** **BLOCKED**）。
  Override: env SPD_TOS_VERSION="16.3.1"; TOS 亦可通过 `getprop | grep version` 截取（与 CPU SPD 共用 tos_detect）。

Then sheet rules:
- non-TRMS / TRMS property precheck, WBS dumpsys, vip_page_pool_state, vip_page_pool.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

_skills = Path(__file__).resolve().parents[2]
_shared = _skills / "spd-shared" / "scripts"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))
import tos_detect  # noqa: E402

# kernel6 及以上：主次版本 >= 6.0（含 6.0.x）
KERNEL_MIN_INCLUSIVE_MM = (6, 0)
# 仅 TOS16.3 及以上：主次版本 >= 16.3
TOS_MIN_INCLUSIVE_MM = (16, 3)

KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")
PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")

TRMS_PROP = "persist.tr_perf.rms.memvip.support"
AEGEAN_PROPS = (
    "persist.tr_perf.aegean.support",
    "persist.tr_perf.aegean.umf.support",
)


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


def parse_props(raw_getprop: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for line in raw_getprop.splitlines():
        match = PROP_LINE_RE.match(line.strip())
        if not match:
            continue
        props[match.group("key")] = match.group("value")
    return props


def parse_kernel_mm_tuple(release: str) -> Optional[Tuple[int, int]]:
    match = KERNEL_MM_RE.search(release)
    if not match:
        return None
    return int(match.group("major")), int(match.group("minor"))


def assert_tos_gate(props: Dict[str, str]) -> None:
    grep_out = run_adb_shell("sh -c \"getprop | grep version\"", allow_nonzero=True)
    print("=== getprop | grep version (TOS / 版本信息截取参考) ===")
    print(grep_out.strip() or "(empty)")
    tos, src = tos_detect.detect_tos_mm_combined(props, grep_out)
    if src and tos:
        print(f"=== TOS parsed (source: {src}) -> {tos[0]}.{tos[1]} ===")
    if tos is None:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- 内存分配支持条件：仅 **TOS16.3 及以上**（主次版本 >= 16.3）")
        print("- 未能解析 TOS：请确认 `getprop | grep version` 中含主次版本（如 16.3），或设置 SPD_TOS_VERSION=16.3.0")
        print(f"- 亦会尝试专用键: {', '.join(tos_detect.TOS_PROP_KEYS_DEFAULT)}")
        sys.exit(2)
    if tos < TOS_MIN_INCLUSIVE_MM:
        print("=== CHECK RESULT: BLOCKED ===")
        print(
            f"- 内存分配支持条件：仅 TOS16.3 及以上（当前解析为 {tos[0]}.{tos[1]}，需 >= {TOS_MIN_INCLUSIVE_MM[0]}.{TOS_MIN_INCLUSIVE_MM[1]}）"
        )
        sys.exit(2)
    print(
        f"TOS gate: pass (>= {TOS_MIN_INCLUSIVE_MM[0]}.{TOS_MIN_INCLUSIVE_MM[1]} -> {tos[0]}.{tos[1]}, source={src})"
    )


def detect_kernel_mm() -> Tuple[int, int]:
    kernel_release = run_adb_shell("uname -r").strip()
    print("=== kernel version ===")
    print(f"uname -r: {kernel_release}")
    kt = parse_kernel_mm_tuple(kernel_release)
    if kt is None:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- cannot parse kernel major.minor from uname -r")
        sys.exit(2)
    print(f"parsed kernel: {kt[0]}.{kt[1]}")
    if kt < KERNEL_MIN_INCLUSIVE_MM:
        print("=== CHECK RESULT: BLOCKED ===")
        print(
            f"- 内存分配支持条件：Linux 内核须为 kernel6 及以上（解析为 >= {KERNEL_MIN_INCLUSIVE_MM[0]}.{KERNEL_MIN_INCLUSIVE_MM[1]}），"
            f"当前为 {kt[0]}.{kt[1]}"
        )
        sys.exit(2)
    print(f"kernel gate: pass (>={KERNEL_MIN_INCLUSIVE_MM[0]}.{KERNEL_MIN_INCLUSIVE_MM[1]} -> {kt[0]}.{kt[1]})")
    return kt


def grep_props(props: Dict[str, str], keywords: Iterable[str]) -> None:
    for key, value in props.items():
        lower = key.lower()
        if any(kw in lower for kw in keywords):
            print(f"[{key}]: [{value}]")


def prop_is_one(props: Dict[str, str], key: str) -> bool:
    return props.get(key) == "1"


def detect_mode(props: Dict[str, str]) -> Tuple[str, Optional[str]]:
    if prop_is_one(props, TRMS_PROP):
        return "trms", TRMS_PROP
    for key in AEGEAN_PROPS:
        if prop_is_one(props, key):
            return "non-trms", key
    return "unknown", None


def check_wbs(mode: str) -> bool:
    if mode == "trms":
        cmd = "dumpsys activity service TranRmsService rms#memvip config_mem_vip"
    else:
        cmd = "dumpsys activity aegean#umf wbs"

    out = run_adb_shell(cmd, allow_nonzero=True)
    print(f"\n=== {cmd} ===")
    print(out.strip() or "(empty output)")

    if mode == "trms":
        compact = re.sub(r"\s+", "", out).lower()
        return "isumfenabletrue" in compact or "isumfenable:true" in compact

    # non-trms expects four signals
    compact = out.lower()
    return (
        "check enable:true" in compact
        and "check init:true" in compact
        and ("check kernel:1" in compact or "check kernel:true" in compact)
        and "check pool:true" in compact
    )


def check_vip_pool_state() -> bool:
    cmd = "cat /proc/priority_allocate/vip_page_pool_state"
    out = run_adb_shell(cmd, allow_nonzero=True)
    print(f"\n=== {cmd} ===")
    print(out.strip() or "(empty output)")
    lower = out.lower()

    # page pool setup must be 1; fillthread setup preferred but optional
    setup_ok = bool(re.search(r"vip_page_pool_setup:\s*1\b", lower))
    fillthread_ok = bool(re.search(r"vip_page_fillthread_setup:\s*1\b", lower))
    return setup_ok and fillthread_ok


def check_vip_pool_stats() -> bool:
    cmd = "cat /proc/priority_allocate/vip_page_pool"
    out = run_adb_shell(cmd, allow_nonzero=True)
    print(f"\n=== {cmd} ===")
    print(out.strip() or "(empty output)")
    lower = out.lower()

    total_matches = [int(x) for x in re.findall(r"total_used:(\d+)", lower)]
    pcp_matches = [int(x) for x in re.findall(r"pcp_used:(\d+)", lower)]
    if not total_matches or not pcp_matches:
        return False
    return any(v > 0 for v in total_matches) and any(v > 0 for v in pcp_matches)


def main() -> None:
    detect_kernel_mm()
    props = parse_props(run_adb_shell("getprop", allow_nonzero=True))
    assert_tos_gate(props)

    print("=== getprop | grep aegean/rms/memvip ===")
    grep_props(props, ["aegean", "rms", "memvip"])

    mode, key = detect_mode(props)
    if mode == "unknown":
        print("\n=== CHECK RESULT: FAIL ===")
        print("- cannot determine execution mode from props")
        print(f"- expected {TRMS_PROP}=1 (TRMS) or any of {AEGEAN_PROPS}=1 (non-TRMS)")
        sys.exit(1)

    print(f"\nmode: {mode} (matched {key})")

    wbs_ok = check_wbs(mode)
    state_ok = check_vip_pool_state()
    pool_ok = check_vip_pool_stats()

    if wbs_ok and state_ok and pool_ok:
        print("\n=== CHECK RESULT: PASS ===")
        print("- property precheck matched")
        print("- wbs check matched expected result")
        print("- vip_page_pool_state matched expected setup flags")
        print("- vip_page_pool showed used counters > 0")
        sys.exit(0)

    print("\n=== CHECK RESULT: FAIL ===")
    if not wbs_ok:
        print("- WBS check did not match expected signals")
    if not state_ok:
        print("- vip_page_pool_state does not contain expected setup flags (=1)")
    if not pool_ok:
        print("- vip_page_pool does not contain valid used counters (>0)")
    sys.exit(1)


if __name__ == "__main__":
    main()
