#!/usr/bin/env python3
"""
SPD auto check: 感知调度 3.0 (Perception Scheduling / transched).

对齐维测 checklist「检查接口」：
- getprop 中与 transched / trans_sched 相关的属性（含 vendor trans_sched 服务：HIDL 或 AIDL）
- cat /proc/trans_scheduler/enable
- dumpsys activity aegean#uias_test_api（接口连通性关键日志；若镜像无该 dumper 则仅告警不 FAIL）

「检查功能 / 稳定性」依赖 root、长驻 dmesg/trace 与人工操作，见 SKILL.md；可用环境变量跳过 dumpsys。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from typing import Dict, List, Tuple

# Sheet + 清单图：0xff / 0x1ff / 0x2ff / 0x3ff / 0x7ff；保留历史表内其它合法掩码。
VALID_ENABLE = {
    0xFF,
    0x1FF,
    0x2FF,
    0x3FF,
    0x7FF,
    0x11,
    0x17,
    0x1F,
    0x5F,
    0x7F,
}

SUPPORTED_KERNELS = {"5.15", "6.1", "6.6", "6.12"}
KERNEL_MM_RE = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)")
PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")

# 产线可能为 HIDL init 名或 AIDL init 名（如 trans_sched_aidl）。
INIT_SVC_KEYS = (
    "init.svc.vendor.trans_sched",
    "init.svc.vendor.trans_sched_aidl",
)
SUPPORT_PROPS = {
    "ro.product.transched.support": "1",
    "ro.vendor.transched.support": "1",
}
VERSION_KEY = "ro.vendor.transched.version"
# 清单说明版本号不严格固定为 v2.0，仅要求存在且形如产线版本串。
VERSION_RE = re.compile(r"^v\d+(\.\d+)*", re.I)

# dumpsys 必须全部命中（接口连通最小闭环）；其余为清单扩展项，缺失仅警告。
DUMPSYS_CORE_MARKERS = [
    "SchedCapHIDL",
    "isReady() completed",
    "getTranSchedState() result:",
    "setTranSchedState(255) result: true",
    "dumpTranSchedUxInfo() result: true",
]

DUMPSYS_EXTENDED_MARKERS = [
    "getCloudState() result:",
    "getTranSchedScene() result:",
    "setTranSchedScene(1) result: true",
    "setTranSchedUxTagsByName(1, ux_exact_test) result: true",
    "getTranSchedUxTags(1) result:",
    "setTranSchedUxThPrio(1, 1) result: true",
    "getTranSchedUxInfo(1)",
    "cancelTranSchedUxTags(1) result: true",
]


def run_adb_shell(command: str) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["adb", "shell", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        print("ERROR: adb not found in PATH.", file=sys.stderr)
        return 127, "", "adb not found"

    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, proc.stdout or "", out


def parse_props(raw: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for line in raw.splitlines():
        m = PROP_LINE_RE.match(line.strip())
        if m:
            props[m.group("key")] = m.group("value")
    return props


def detect_kernel_mm() -> str:
    code, stdout, _ = run_adb_shell("uname -r")
    if code != 0:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- failed to read kernel version (uname -r)")
        sys.exit(2)
    kernel_release = stdout.strip()
    print("=== kernel version ===")
    print(f"uname -r: {kernel_release}")
    m = KERNEL_MM_RE.search(kernel_release)
    if not m:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- cannot parse kernel major.minor")
        sys.exit(2)
    mm = f"{m.group('major')}.{m.group('minor')}"
    print(f"parsed kernel: {mm}")
    if mm not in SUPPORTED_KERNELS:
        print("=== CHECK RESULT: BLOCKED ===")
        print(f"- kernel {mm} not in supported list for this sheet: {sorted(SUPPORTED_KERNELS)}")
        sys.exit(2)
    print(f"kernel support (sheet): yes ({mm})")
    return mm


def parse_enable_value(raw: str) -> int | None:
    text = raw.strip().lower()
    if not text:
        return None
    m = re.search(r"(?:enable\s*=\s*)?(0x[0-9a-f]+|[0-9]+)", text, re.I)
    if not m:
        return None
    s = m.group(1)
    return int(s, 0)


def filter_transched_props(props: Dict[str, str]) -> List[Tuple[str, str]]:
    rows: List[Tuple[str, str]] = []
    for k, v in sorted(props.items()):
        kl = k.lower()
        if "transched" in kl or "trans_sched" in kl:
            rows.append((k, v))
    return rows


def validate_version(val: str | None) -> Tuple[bool, str]:
    if val is None:
        return False, "missing"
    s = val.strip()
    if not s:
        return False, "empty"
    if VERSION_RE.match(s):
        return True, s
    return False, f"not version-like: {s!r}"


def aegean_uias_dumpsys_absent(text: str) -> bool:
    """部分版本镜像未注册 aegean#uias_test_api dumper，属已知差异。"""
    t = text.lower()
    return "no dumper for feature" in t and "aegean" in t


def vendor_trans_sched_running(props: Dict[str, str]) -> Tuple[bool, str]:
    """任一 vendor trans_sched（HIDL/AIDL）init 为 running 即通过。"""
    for k in INIT_SVC_KEYS:
        if props.get(k) == "running":
            return True, k
    parts = ", ".join(f"{k}={props.get(k)!r}" for k in INIT_SVC_KEYS)
    return False, parts


def check_dumpsys_connectivity() -> Tuple[bool, List[str], List[str], str, bool]:
    """
    使用 device sh 双引号包裹整条命令，避免 # 被 shell 当成注释截断。

    返回 (ok, missing_core, missing_ext, text, no_dumper_build)。
    no_dumper_build 为 True 时：不将 dumpsys 记为失败（镜像无测试接口）。
    """
    cmd = 'sh -c "dumpsys activity aegean#uias_test_api"'
    code, stdout, combined = run_adb_shell(cmd)
    text = (stdout or "") + (combined if not stdout else "")
    missing_core: List[str] = []
    missing_ext: List[str] = []
    if code != 0:
        return False, [f"dumpsys exit code {code}"], [], text, False
    stripped = text.strip()
    if len(stripped) < 20:
        return False, ["dumpsys output too short (service missing or permission?)"], [], text, False

    if aegean_uias_dumpsys_absent(text):
        return True, [], [], text, True

    if len(stripped) < 80:
        return False, ["dumpsys output too short (unexpected)"], [], text, False

    for marker in DUMPSYS_CORE_MARKERS:
        if marker not in text:
            missing_core.append(f"missing core marker: {marker}")

    for marker in DUMPSYS_EXTENDED_MARKERS:
        if marker not in text:
            missing_ext.append(marker)

    ok = not missing_core
    return ok, missing_core, missing_ext, text, False


def main() -> None:
    detect_kernel_mm()

    skip_dumpsys = os.environ.get("SPD_SKIP_TRANCHED_DUMPSYS", "").strip() in ("1", "true", "yes")

    code, getprop_out, _ = run_adb_shell("getprop")
    if code != 0:
        print("=== CHECK RESULT: BLOCKED ===")
        print("- getprop failed")
        sys.exit(2)

    props = parse_props(getprop_out)
    filtered = filter_transched_props(props)
    print("=== getprop | grep -E \"transched|trans_sched\" (parsed) ===")
    if filtered:
        for k, v in filtered:
            print(f"[{k}]: [{v}]")
    else:
        print("(no matching props)")

    failed: List[str] = []

    for k, exp in SUPPORT_PROPS.items():
        act = props.get(k)
        if act != exp:
            failed.append(f"{k}: expected '{exp}', actual {act!r}")

    ver = props.get(VERSION_KEY)
    ver_ok, ver_reason = validate_version(ver)
    if not ver_ok:
        failed.append(f"{VERSION_KEY}: {ver_reason}")
    else:
        print(f"\n=== {VERSION_KEY} (non-strict, checklist) ===")
        print(f"OK: {ver_reason}")

    svc_ok, svc_detail = vendor_trans_sched_running(props)
    if not svc_ok:
        failed.append(f"vendor trans_sched service: none running ({svc_detail})")

    code, enable_out, _ = run_adb_shell("cat /proc/trans_scheduler/enable")
    print("\n=== cat /proc/trans_scheduler/enable ===")
    print(enable_out.strip() or "(empty)")
    enable_val = parse_enable_value(enable_out)
    enable_ok = enable_val is not None and enable_val in VALID_ENABLE
    if not enable_ok:
        failed.append(
            f"/proc/trans_scheduler/enable: expected one of "
            f"{sorted(hex(x) for x in VALID_ENABLE)}, parsed {enable_val!r}"
        )

    dumpsys_ok = True
    dumpsys_missing_core: List[str] = []
    dumpsys_missing_ext: List[str] = []
    dumpsys_no_dumper = False
    dumpsys_snip = ""
    if skip_dumpsys:
        print("\n=== dumpsys activity aegean#uias_test_api ===")
        print("(skipped: SPD_SKIP_TRANCHED_DUMPSYS=1)")
    else:
        print("\n=== dumpsys activity aegean#uias_test_api ===")
        dumpsys_ok, dumpsys_missing_core, dumpsys_missing_ext, full, dumpsys_no_dumper = (
            check_dumpsys_connectivity()
        )
        dumpsys_snip = full[:4000] if full else ""
        if len(full) > 4000:
            print("(first 4000 chars)")
        print(dumpsys_snip or "(no output)")
        if dumpsys_no_dumper:
            print(
                "\n=== dumpsys: no Aegean uias dumper in this build ===\n"
                "(skipped interface gate; use a build with aegean#uias_test_api or set "
                "SPD_SKIP_TRANCHED_DUMPSYS=1)"
            )
        elif not dumpsys_ok:
            for m in dumpsys_missing_core:
                print(f"DUMPSYS: {m}", file=sys.stderr)
            failed.append("dumpsys aegean#uias_test_api: interface connectivity check failed")
        elif dumpsys_missing_ext:
            print("\n=== dumpsys extended markers (optional, checklist) ===")
            print(f"- missing {len(dumpsys_missing_ext)} extended line(s); review full log if needed")

    if failed:
        print("\n=== CHECK RESULT: FAIL ===")
        for line in failed:
            print(f"- {line}")
        sys.exit(1)

    print("\n=== CHECK RESULT: PASS ===")
    for k, v in SUPPORT_PROPS.items():
        print(f"- {k} = {v}")
    if ver is not None:
        print(f"- {VERSION_KEY} = {ver.strip()} (version format OK)")
    print(f"- vendor trans_sched running: {svc_detail}")
    print(f"- trans_scheduler enable = {hex(enable_val)} (allowed)")
    if skip_dumpsys:
        print("- dumpsys connectivity: skipped")
    elif dumpsys_no_dumper:
        print("- dumpsys connectivity: no dumper in build (not gated)")
    else:
        print("- dumpsys connectivity: core markers present")
        if dumpsys_missing_ext:
            print(f"- dumpsys extended: {len(dumpsys_missing_ext)} optional marker(s) absent")

    sys.exit(0)


if __name__ == "__main__":
    main()
