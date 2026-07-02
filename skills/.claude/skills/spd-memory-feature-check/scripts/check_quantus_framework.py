#!/usr/bin/env python3
"""
SPD auto check: 内存管理 Quantus 框架.

前提：TOS 主次版本须 **>= 16.3**（与 `tos_detect` 一致：`SPD_TOS_VERSION` → 专用属性 →
`getprop | grep version`）。

分支：
- **kernel6 及以上**（uname 解析 (major,minor) >= (6,0)，且非表内 6.6 / 6.12 专项不支持）：
  沿用原截图逻辑：`page_filter_state` 为使能（**1** 或 **1:*** 前缀），且存在 quantus 相关属性。
- **kernel < 6**（如 5.15）且仍 **TOS>=16.3**：补充路径 ——
  `page_filter_state` **取值须为 1**（严格，不接受仅 `1:2` 类多段值作通过）；
  `getprop | grep quantus` 涉及的每条属性 **值均为 1**。
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, Tuple

_skills = Path(__file__).resolve().parents[2]
_shared = _skills / "spd-shared" / "scripts"
if str(_shared) not in sys.path:
    sys.path.insert(0, str(_shared))
import tos_detect  # noqa: E402

# 表内仍标记为 Quantus 专项不支持的 Linux 主次版本（kernel6+ 分支下 BLOCKED）
UNSUPPORTED_KERNEL_MM = frozenset({"6.6", "6.12"})
TOS_MIN_INCLUSIVE_MM = (16, 3)
KERNEL_SIX_INCLUSIVE_MM = (6, 0)

KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")
PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")


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


def parse_kernel_tuple(release: str) -> Tuple[int, int] | None:
    match = KERNEL_MM_RE.search(release)
    if not match:
        return None
    return int(match.group("major")), int(match.group("minor"))


def extract_page_filter_value(raw: str) -> str:
    """Handle `1`, `1:2`, or `page_filter_state:     1` style lines."""
    s = raw.strip()
    if not s:
        return ""
    m = re.search(r"page_filter_state\s*:\s*(\S+)", s, re.I)
    if m:
        return m.group(1).strip()
    return s.splitlines()[0].strip()


def page_filter_relaxed_ok(raw: str) -> bool:
    v = extract_page_filter_value(raw)
    return v == "1" or v.startswith("1:")


def page_filter_strict_one(raw: str) -> bool:
    """kernel < 6 补充路径：须严格为 1（与飞书「结果为 1」一致）。"""
    return extract_page_filter_value(raw) == "1"


def quantus_props_all_values_one(props: Dict[str, str]) -> bool:
    items = [(k, v) for k, v in props.items() if "quantus" in k.lower()]
    if not items:
        return False
    return all(v.strip() == "1" for _, v in items)


def quantus_props_exist(props: Dict[str, str]) -> bool:
    return any("quantus" in k.lower() for k in props)


def assert_tos_16_3(props: Dict[str, str], grep_version: str) -> Tuple[int, int]:
    tos, src = tos_detect.detect_tos_mm_combined(props, grep_version)
    print("=== TOS (Quantus 前提 >=16.3) ===")
    if tos is None:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- Quantus 检查需先解析 TOS >= 16.3；未能解析")
        print("- 请设置 SPD_TOS_VERSION=16.3.x 或确认 getprop / 专用 TOS 属性 / getprop|grep version")
        sys.exit(2)
    print(f"parsed TOS {tos[0]}.{tos[1]} (source={src}), need >= {TOS_MIN_INCLUSIVE_MM[0]}.{TOS_MIN_INCLUSIVE_MM[1]}")
    if tos < TOS_MIN_INCLUSIVE_MM:
        print("=== CHECK RESULT: BLOCKED ===")
        print(f"- Quantus 自动化仅适用于 TOS16.3 及以上，当前 {tos[0]}.{tos[1]}")
        sys.exit(2)
    return tos


def main() -> None:
    kernel_release = run_adb_shell("uname -r").strip()
    print("=== kernel version ===")
    print(f"uname -r: {kernel_release}")
    kt = parse_kernel_tuple(kernel_release)
    if kt is None:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- cannot parse kernel major.minor from uname -r")
        sys.exit(2)
    kstr = f"{kt[0]}.{kt[1]}"
    print(f"parsed kernel: {kstr}")

    getprop_out = run_adb_shell("getprop", allow_nonzero=True)
    props = parse_props(getprop_out)
    grep_ver = run_adb_shell("sh -c \"getprop | grep version\"", allow_nonzero=True)
    assert_tos_16_3(props, grep_ver)

    if kstr in UNSUPPORTED_KERNEL_MM:
        print("=== CHECK RESULT: BLOCKED ===")
        print(f"- kernel {kstr} is marked as not supported for Quantus (kernel6+ branch)")
        sys.exit(2)

    state_out = run_adb_shell("cat /proc/pages_prefiltered/page_filter_state", allow_nonzero=True)
    quantus_grep = run_adb_shell("sh -c \"getprop | grep quantus\"", allow_nonzero=True)

    print("\n=== cat /proc/pages_prefiltered/page_filter_state ===")
    print(state_out.strip() or "(empty output)")

    print("\n=== getprop | grep quantus ===")
    print(quantus_grep.strip() or "(no lines)")

    low_kernel = kt < KERNEL_SIX_INCLUSIVE_MM
    branch = "TOS>=16.3 & kernel<6 (strict page_filter_state==1, quantus props all 1)" if low_kernel else (
        "TOS>=16.3 & kernel>=6 (relaxed state + quantus props present)"
    )
    print(f"\n=== check branch ===\n{branch}")

    if low_kernel:
        ok_state = page_filter_strict_one(state_out)
        ok_q = quantus_props_all_values_one(props)
        if ok_state and ok_q:
            print("\n=== CHECK RESULT: PASS ===")
            print("- page_filter_state value is exactly 1")
            print("- all quantus-related getprop values are 1")
            sys.exit(0)
        print("\n=== CHECK RESULT: FAIL ===")
        if not ok_state:
            v = extract_page_filter_value(state_out)
            print(f"- expected page_filter_state value exactly '1', got {v!r}")
        if not ok_q:
            if not quantus_props_exist(props):
                print("- no quantus properties in getprop")
            else:
                bad = [(k, props[k]) for k in props if "quantus" in k.lower() and props[k].strip() != "1"]
                print("- quantus properties not all 1:")
                for k, v in bad[:12]:
                    print(f"  [{k}]: [{v}]")
        sys.exit(1)

    # kernel >= 6.0 and not 6.6/6.12
    ok_state = page_filter_relaxed_ok(state_out)
    ok_q = quantus_props_exist(props)
    if ok_state and ok_q:
        print("\n=== CHECK RESULT: PASS ===")
        print("- page_filter_state indicates enabled (1 or 1:*)")
        print("- at least one quantus-related property present")
        sys.exit(0)

    print("\n=== CHECK RESULT: FAIL ===")
    if not ok_state:
        print("- page_filter_state does not indicate enabled state (expected 1 or 1:*)")
    if not ok_q:
        print("- no quantus property found")
    sys.exit(1)


if __name__ == "__main__":
    main()
