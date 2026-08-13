#!/usr/bin/env python3
"""
SPD auto check: CPU 健康标准检查（维测表三项，须全部通过才 PASS）。

1) getprop ro.product.transchedmetrics.support -> 1
2) dumpsys（按 TOS 分支），回显须为 trancpufreqtime 的 usage/help（含子命令）:
   - TOS < 16.3: dumpsys tran_service_manager trancpufreqtime help
   - TOS >= 16.3: dumpsys tran_system_server_service_manager -service trancpufreqtime help
3) 可成功进入目录: cd /sys/kernel/tran_health_sched/（脚本用 cd && pwd + ls 校验可访问性）

TOS: 环境变量 SPD_TOS_VERSION；或 tos_detect 从 getprop 解析。
"""

from __future__ import annotations

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

PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")


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
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def parse_props(raw: str) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in raw.splitlines():
        m = PROP_LINE_RE.match(line.strip())
        if m:
            props[m.group("key")] = m.group("value")
    return props


def is_tos_16_3_or_later(mm: tuple[int, int] | None) -> bool:
    if mm is None:
        return False
    maj, mino = mm
    if maj > 16:
        return True
    if maj == 16 and mino >= 3:
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


def dumpsys_trancpufreqtime_help(use_new: bool) -> tuple[int, str]:
    if use_new:
        cmd = "dumpsys tran_system_server_service_manager -service trancpufreqtime help"
    else:
        cmd = "dumpsys tran_service_manager trancpufreqtime help"
    return run_adb_shell(cmd)


def dumpsys_help_matches_sheet(text: str) -> tuple[bool, list[str]]:
    """
    期望结果（维测表）: 回显含 `usage: trancpufreqtime ...` 形态及子命令
    process / kthread / cpu_loading / cpu / debug / clear / help。
    在整段回显中校验（若仅有异常栈而无 help 正文则 FAIL）。
    """
    t = text.lower()
    missing: list[str] = []

    if not re.search(r"usage\s*:\s*trancpufreqtime", t, re.I):
        missing.append("usage: trancpufreqtime（维测示例行）")

    for needle, label in (
        ("process", "子命令 process"),
        ("kthread", "子命令 kthread"),
        ("cpu_loading", "子命令 cpu_loading"),
        ("debug", "子命令 debug"),
        ("clear", "子命令 clear"),
    ):
        if needle not in t:
            missing.append(label)

    if not re.search(r"\bcpu\b", t):
        missing.append("子命令 cpu（词边界，避免仅 cpu_loading）")
    if not re.search(r"\bhelp\b", t):
        missing.append("子命令 help")

    return len(missing) == 0, missing


def check_item1_transchedmetrics(props: dict[str, str]) -> bool:
    print("=== [1/3] 检查项: ro.product.transchedmetrics.support ===")
    metrics = props.get("ro.product.transchedmetrics.support", "").strip()
    print("命令: getprop ro.product.transchedmetrics.support")
    print(f"实际值: {metrics or '(empty)'}")
    print("期望结果: 1")
    ok = metrics == "1"
    print(f"结果: {'PASS' if ok else 'FAIL'}")
    return ok


def check_item2_dumpsys_trancpufreqtime_help(
    props: dict[str, str], gv: str
) -> tuple[bool, str]:
    """Returns (ok, reason_if_fail)."""
    print("\n=== [2/3] 检查项: dumpsys trancpufreqtime help（按 TOS 分支） ===")

    print("=== getprop | grep version (TOS / 版本截取参考) ===")
    print((gv.strip() or "(empty)")[:8000])

    tos_mm, tos_src = tos_detect.detect_tos_mm_combined(props, gv)
    if tos_mm is not None:
        print(f"=== TOS parsed (source: {tos_src}) -> {tos_mm[0]}.{tos_mm[1]} ===")
    else:
        print("=== TOS version ===")
        print("(not detected: set SPD_TOS_VERSION 或依赖 getprop 中 TOS 相关属性；将依次尝试两种 dumpsys)")

    use_new = is_tos_16_3_or_later(tos_mm)
    if tos_mm is None:
        order = [False, True]
    else:
        order = [use_new, not use_new]

    last_code, last_out = 0, ""
    last_missing: list[str] = []
    dumpsys_ok = False
    dumpsys_tag = ""

    for prefer_new in order:
        c, o = dumpsys_trancpufreqtime_help(prefer_new)
        last_code, last_out = c, o
        tag = "TOS16.3+ path" if prefer_new else "legacy (< TOS16.3) path"
        cmd = (
            "dumpsys tran_system_server_service_manager -service trancpufreqtime help"
            if prefer_new
            else "dumpsys tran_service_manager trancpufreqtime help"
        )
        print(f"\n命令 ({tag}): {cmd}")
        snippet = o.strip()[:4000]
        print(snippet or "(empty)")
        if len(o.strip()) > 4000:
            print(f"... ({len(o.splitlines())} lines total, truncated for display)")

        errish = re.search(
            r"Can't find service|Unknown command|does not exist|Permission denied",
            o,
            re.I,
        )
        sheet_ok, missing = dumpsys_help_matches_sheet(o)
        last_missing = missing

        if c == 0 and o.strip() and not errish and sheet_ok:
            dumpsys_ok = True
            dumpsys_tag = tag
            break
        if c == 0 and o.strip() and not errish and not sheet_ok:
            print("\n--- dumpsys 有输出，但与维测表期望的 usage/help 不一致 ---")
            for m in missing:
                print(f"  - missing: {m}")

    if dumpsys_ok:
        print(f"\n期望结果: usage: trancpufreqtime ... 及子命令说明")
        print(f"结果: PASS ({dumpsys_tag})")
        return True, ""

    reason_parts: list[str] = []
    if last_out.strip() and last_missing:
        reason_parts.append("dumpsys 回显缺少维测表要求的 usage/子命令")
        reason_parts.extend(f"  - {m}" for m in last_missing)
    else:
        reason_parts.append("dumpsys 无有效 help 或服务不可用")
    reason_parts.append(f"last adb exit code: {last_code}")
    print("\n结果: FAIL")
    return False, "\n".join(reason_parts)


def check_item3_tran_health_sched_dir() -> bool:
    print("\n=== [3/3] 检查项: 可进入 /sys/kernel/tran_health_sched/ ===")
    print("命令: cd /sys/kernel/tran_health_sched && pwd")
    code, pwd_out = run_adb_shell("cd /sys/kernel/tran_health_sched && pwd")
    print((pwd_out.strip() or "(empty)"))
    if code != 0:
        print("期望结果: 可成功进入该目录（pwd 在 tran_health_sched 下）")
        print("结果: FAIL")
        return False
    pwd_line = pwd_out.strip().splitlines()[-1] if pwd_out.strip() else ""
    if "tran_health_sched" not in pwd_line.replace("\\", "/"):
        print("期望结果: pwd 路径包含 tran_health_sched")
        print("结果: FAIL")
        return False

    code, hs_out = run_adb_shell("ls /sys/kernel/tran_health_sched")
    print("\n命令: ls /sys/kernel/tran_health_sched（校验可访问）")
    print(hs_out.strip() or "(empty)")
    if code != 0 or "No such file" in hs_out or "not found" in hs_out.lower():
        print("结果: FAIL（目录不可列举）")
        return False
    print("结果: PASS")
    return True


def main() -> None:
    detect_kernel_mm()

    code, raw = run_adb_shell("getprop")
    if code != 0:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- getprop failed")
        sys.exit(2)
    props = parse_props(raw)

    _gc, gv = run_adb_shell("sh -c \"getprop | grep version\"")
    item1 = check_item1_transchedmetrics(props)
    item2, item2_detail = check_item2_dumpsys_trancpufreqtime_help(props, gv)
    item3 = check_item3_tran_health_sched_dir()

    print("\n=== 三项汇总 ===")
    print(f"- [1] ro.product.transchedmetrics.support == 1: {'PASS' if item1 else 'FAIL'}")
    print(f"- [2] dumpsys trancpufreqtime help（维测 usage/子命令）: {'PASS' if item2 else 'FAIL'}")
    print(f"- [3] /sys/kernel/tran_health_sched 可进入且可访问: {'PASS' if item3 else 'FAIL'}")

    if item1 and item2 and item3:
        print("\n=== CHECK RESULT: PASS ===")
        print("- 三项检查全部通过")
        sys.exit(0)

    print("\n=== CHECK RESULT: FAIL ===")
    print("- 三项未全部通过（维测要求全部 PASS 才通过）")
    if not item2 and item2_detail:
        print(item2_detail)
    sys.exit(1)


if __name__ == "__main__":
    main()
