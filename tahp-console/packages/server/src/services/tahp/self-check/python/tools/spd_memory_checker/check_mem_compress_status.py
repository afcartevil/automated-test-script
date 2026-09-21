#!/usr/bin/env python3
"""
内存压缩（SPD）：先判定本设备**唯一应检版本**，再**仅执行该版本**对应检查；默认报告只含「内存压缩」feature 结论。

判定优先级（与本设备只需满足一种实现一致）：
1) **内存压缩 2.0（新内存融合）**：`memcgcprsv2.support==true`，或 **TOS≥16.3 ∧ kernel≥6.1**（必开 2.0）→ 仅跑 `evaluate_mem_compress_2_0`
2) **内存压缩 1.1（飞书表路径）**：不满足上一档，且 kernel ∈ {6.1, 6.12}（脚本矩阵）→ 仅跑 `evaluate_mem_compress_v11`
3) **其它**：kernel 不支持或未覆盖 → BLOCKED，不执行上述任一压缩路径

说明：`detect_memfusion_compress_version.detect_compress` 仅作**运行时画像**，可能与「应检版本」不一致；
默认报告**不**输出该项（避免与 SPD「单版本承诺」混淆）；`--verbose` 可打印。
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

_SHARED = _SCRIPT_DIR.parent / "spd_shared" / "scripts"
if _SHARED.is_dir() and str(_SHARED) not in sys.path:
    sys.path.insert(0, str(_SHARED))

import check_mem_compress_2_0 as mc20
import check_mem_compress as mc11
import detect_memfusion_compress_version as dmv
import evidence_report as evr


VERSION_PROP_KEYS: Tuple[str, ...] = (
    "persist.sys.ota_version",
    "ro.tran.bootimage.version",
    "ro.tran.odm.version",
    "ro.tran.odm_dlkm.version",
    "ro.tran.product.version",
    "ro.tran.system.version",
    "ro.tran.system_dlkm.version",
    "ro.tran.system_ext.version",
    "ro.tran.tr_product.version",
    "ro.tran.tr_region.version",
    "ro.tran.vendor_dlkm.version",
)

_SEMVER_TRIPLE_RE = re.compile(
    r"(?:^|[^\d])(?P<maj>\d{1,2})\.(?P<min>\d{1,2})\.(?P<pat>\d{1,4})(?:[^\d]|$)"
)


def adb_ok() -> bool:
    try:
        proc = subprocess.run(
            ["adb", "shell", "echo ok"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return False
    return proc.returncode == 0


def kernel_mm_soft() -> Tuple[Optional[str], str]:
    rc, out = mc11.run_adb_shell_soft("uname -r")
    if rc != 0:
        return None, ""
    mm = mc11.parse_kernel_mm_from_uname(out.strip())
    return mm, out.strip()


def kernel_ge_6_1(kernel_mm: str) -> bool:
    try:
        parts = kernel_mm.split(".", 1)
        maj, minr = int(parts[0]), int(parts[1])
        return (maj, minr) >= (6, 1)
    except (ValueError, IndexError):
        return False


def _triple_ge_tos_16_3(maj: int, minr: int) -> bool:
    return maj > 16 or (maj == 16 and minr >= 3)


def infer_tos_ge_16_3(props: Dict[str, str]) -> Tuple[bool, str, List[str]]:
    evidence: List[str] = []
    hit_163_dot_keys: List[str] = []

    for key in VERSION_PROP_KEYS:
        val = (props.get(key) or "").strip()
        if not val:
            continue
        evidence.append(f"{key}=[{val}]")
        if "16.3." in val:
            hit_163_dot_keys.append(key)

    if hit_163_dot_keys:
        return (
            True,
            f"属性值中含片段「16.3.」（键: {', '.join(hit_163_dot_keys)}）",
            evidence,
        )

    best: Optional[Tuple[int, int, str]] = None
    for key in VERSION_PROP_KEYS:
        val = props.get(key) or ""
        for m in _SEMVER_TRIPLE_RE.finditer(val):
            maj_s, min_s = m.group("maj"), m.group("min")
            try:
                maj, minr = int(maj_s), int(min_s)
            except ValueError:
                continue
            if _triple_ge_tos_16_3(maj, minr):
                if best is None or (maj, minr) > (best[0], best[1]):
                    best = (maj, minr, key)

    if best is not None:
        return (
            True,
            f"解析到主次版本 {best[0]}.{best[1]}（≥16.3），来源键 {best[2]}",
            evidence,
        )

    if not evidence:
        return (
            False,
            "列举的 version 属性均无取值，无法判定 TOS≥16.3（未套用必开 2.0 规则）",
            [],
        )
    return (
        False,
        "列举属性中未命中「16.3.」且无解析为 ≥16.3 的 x.y.z（保守判定为未满足 TOS≥16.3）",
        evidence,
    )


def resolve_expected_mem_compress(
    kernel_mm: str,
    mf: Dict[str, str],
    props_full: Dict[str, str],
    rc_gp: int,
) -> Tuple[
    str,
    str,
    str,
    bool,
    bool,
    str,
    List[str],
    bool,
]:
    """
    返回：expected_track, expected_label, check_executed,
          rsv2_on, policy_must_2_0, tos_note, tos_evidence, k_ge_61
    """
    rsv2_raw = mf.get(dmv.MEMCG_RSV2_PROP, "").strip().lower()
    rsv2_on = rsv2_raw == "true"

    if rc_gp != 0:
        tos_ge_16_3 = False
        tos_note = "adb shell getprop 失败，无法检索 version 属性（未套用必开 2.0 规则）"
        tos_evidence: List[str] = []
    else:
        tos_ge_16_3, tos_note, tos_evidence = infer_tos_ge_16_3(props_full)

    k_ge_61 = kernel_ge_6_1(kernel_mm)
    policy_must_2_0 = tos_ge_16_3 and k_ge_61

    if rsv2_on or policy_must_2_0:
        parts: List[str] = []
        if rsv2_on:
            parts.append("产品开关 memcgcprsv2.support=true")
        if policy_must_2_0:
            parts.append("项目规则 TOS≥16.3 且 kernel≥6.1（必开 2.0）")
        label = "内存压缩 2.0（新内存融合）"
        if parts:
            label = f"{label} — " + "；".join(parts)
        return "2.0_new", label, "mem_compress_2.0", rsv2_on, policy_must_2_0, tos_note, tos_evidence, k_ge_61

    if kernel_mm in mc11.SUPPORTED_V11_KERNELS:
        return (
            "1.1",
            f"内存压缩 1.1（飞书表路径；kernel={kernel_mm}）",
            "mem_compress_1.1",
            rsv2_on,
            policy_must_2_0,
            tos_note,
            tos_evidence,
            k_ge_61,
        )

    if kernel_mm in mc11.UNSUPPORTED_KERNELS:
        return (
            "none",
            f"无本专项自动化要求（kernel {kernel_mm} 在表截图中标记为不支持）",
            "none",
            rsv2_on,
            policy_must_2_0,
            tos_note,
            tos_evidence,
            k_ge_61,
        )

    if kernel_mm in mc11.UNKNOWN_KERNELS:
        return (
            "unknown",
            f"kernel {kernel_mm} 支持状态未在脚本矩阵明确（请对照飞书）",
            "none",
            rsv2_on,
            policy_must_2_0,
            tos_note,
            tos_evidence,
            k_ge_61,
        )

    return (
        "unknown",
        f"kernel {kernel_mm} 未覆盖（应检版本请对照飞书）",
        "none",
        rsv2_on,
        policy_must_2_0,
        tos_note,
        tos_evidence,
        k_ge_61,
    )


def run_single_check(
    expected_track: str,
    mf: Dict[str, str],
    dump_info: str,
    zram_bd: str,
) -> Tuple[str, List[str], List[evr.EvidenceRow]]:
    """返回 feature_status, detail_lines, evidence_rows。"""
    detail: List[str] = []
    rows: List[evr.EvidenceRow] = []

    if expected_track == "2.0_new":
        # 单版本入口：memcgcprsv2 只用于上面的应检路由，不作为本项 PASS/FAIL 证据
        ok, rows = mc20.evaluate_mem_compress_2_0_rows(
            mf, dump_info, zram_bd, require_rsv2=False
        )
        if not ok:
            detail.extend(f"{r.name}: 预期={r.expected}, 实际={r.actual}" for r in rows if not r.ok)
        return ("PASS" if ok else "FAIL", detail, rows)

    if expected_track == "1.1":
        st, reasons, _d, _m = mc11.evaluate_mem_compress_v11()
        if st == "BLOCKED":
            detail.extend(reasons)
            rows.append(evr.row("内存压缩 1.1 路径", "可执行并 PASS", "BLOCKED: " + "; ".join(reasons[:3]), False))
            return "BLOCKED", detail, rows
        if st == "PASS":
            rows.append(evr.row("内存压缩 1.1 路径", "wbs pass=true + memcg_compress on", "PASS", True))
            return "PASS", detail, rows
        detail.extend(reasons)
        rows.append(evr.row("内存压缩 1.1 路径", "wbs pass=true + memcg_compress on", "; ".join(reasons[:4]) or "FAIL", False))
        return "FAIL", detail, rows

    detail.append("未匹配到可执行的压缩版本检查分支。")
    rows.append(evr.row("应检版本路径", "2.0_new 或 1.1", expected_track or "(none)", False))
    return "BLOCKED", detail, rows


def print_verbose(
    uname_line: str,
    kernel_mm: str,
    k_ge_61: bool,
    tos_ge_16_3: bool,
    tos_note: str,
    tos_evidence: List[str],
    policy_must_2_0: bool,
    actual_ver: str,
    actual_reason: str,
) -> None:
    tg163 = tos_ge_16_3  # alias for readability in print
    print("=== 诊断（verbose） ===")
    print(f"uname -r: {uname_line}")
    print(f"parsed kernel major.minor: {kernel_mm}")
    print(f"kernel≥6.1: {k_ge_61}")
    print(f"TOS≥16.3: {tg163}")
    print(f"  依据: {tos_note}")
    if tos_evidence:
        print("  version 属性（节选）:")
        for line in tos_evidence[:12]:
            print(f"    {line}")
        if len(tos_evidence) > 12:
            print(f"    ... 共 {len(tos_evidence)} 条")
    print(f"必开 2.0（TOS≥16.3 ∧ kernel≥6.1）: {policy_must_2_0}")
    print(f"detect_compress（运行时画像，非 SPD 必写字段）: {actual_ver}")
    print(f"  {actual_reason}")


def main() -> None:
    ap = argparse.ArgumentParser(description="SPD 内存压缩：单版本判定 + 单路径检查")
    ap.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="打印内核/TOS/detect 等诊断信息（默认仅输出 feature 报告）",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="输出一行 JSON（仅内存压缩 feature 字段）",
    )
    args = ap.parse_args()

    def sep(title: str) -> None:
        line = "=" * 44
        print(f"\n{line}\n{title}\n{line}")

    if not adb_ok():
        out = {
            "feature": "内存压缩",
            "expected_version": None,
            "expected_label": None,
            "check_executed": None,
            "result": "BLOCKED",
            "details": ["adb 不可用或设备未连接"],
        }
        if args.json:
            print(json.dumps(out, ensure_ascii=False))
        else:
            sep("SPD — 内存压缩")
            print("检查结果: BLOCKED")
            print("说明: adb 不可用或设备未连接。")
        sys.exit(2)

    kernel_mm, uname_line = kernel_mm_soft()
    if kernel_mm is None:
        out = {
            "feature": "内存压缩",
            "expected_version": None,
            "expected_label": None,
            "check_executed": None,
            "result": "BLOCKED",
            "details": [f"无法从 uname 解析 kernel（raw={uname_line!r}）"],
        }
        if args.json:
            print(json.dumps(out, ensure_ascii=False))
        else:
            sep("SPD — 内存压缩")
            print("检查结果: BLOCKED")
            print(f"说明: 无法解析 uname -r。")
        sys.exit(2)

    rc_gp, raw_getprop = mc11.run_adb_shell_soft("getprop")
    props_full: Dict[str, str] = dmv.parse_getprop(raw_getprop) if rc_gp == 0 else {}

    ev = dmv.collect_evidence()
    actual_ver, actual_reason = dmv.detect_compress(ev)
    mf = ev.get("memfusion_props") or {}

    (
        expected_track,
        expected_label,
        check_executed,
        rsv2_on,
        policy_must_2_0,
        tos_note,
        tos_evidence,
        k_ge_61,
    ) = resolve_expected_mem_compress(kernel_mm, mf, props_full, rc_gp)

    if rc_gp != 0:
        tos_ge_16_3 = False
    else:
        tos_ge_16_3 = infer_tos_ge_16_3(props_full)[0]

    detail_extra: List[str] = []
    # rsv2 仅作应检路由信号；缺开关时在 verbose/说明里提示，不计入 FAIL
    if expected_track == "2.0_new" and policy_must_2_0 and not rsv2_on:
        detail_extra.append(
            "提示: 必开 2.0 规则命中但 memcgcprsv2.support 非 true（路由已走 2.0 证据项；开关本身不作为本项 FAIL）"
        )

    feature_status, detail_lines, evidence_rows = run_single_check(
        expected_track,
        mf,
        ev.get("dump_info") or "",
        ev.get("zram_bd_list") or "",
    )
    detail_lines = detail_extra + detail_lines

    # 前置：应检版本本身也作为对比项
    scope_rows = [
        evr.row(
            "本设备应检版本",
            expected_label,
            expected_label,
            True,
        ),
        evr.row(
            "执行的检查",
            check_executed or "(none)",
            check_executed or "(none)",
            bool(check_executed and check_executed != "none"),
        ),
    ]
    if expected_track == "2.0_new":
        # 仅展示路由用到的 rsv2 实值，不参与 OK/FAIL 计数语义（ok=True）
        scope_rows.append(
            evr.row(
                "路由信号 memcgcprsv2（非判定项）",
                "true 则可直接路由 2.0；亦可由 TOS≥16.3∧kernel≥6.1 路由",
                "true" if rsv2_on else (mf.get(dmv.MEMCG_RSV2_PROP) or "(missing)"),
                True,
            )
        )

    payload: Dict[str, Any] = {
        "feature": "内存压缩",
        "expected_version": expected_track,
        "expected_label": expected_label,
        "check_executed": check_executed,
        "result": feature_status,
        "details": detail_lines,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
        sys.exit(0 if feature_status == "PASS" else (1 if feature_status == "FAIL" else 2))

    if args.verbose:
        print_verbose(
            uname_line,
            kernel_mm,
            k_ge_61,
            tos_ge_16_3,
            tos_note,
            tos_evidence,
            policy_must_2_0,
            actual_ver,
            actual_reason,
        )

    sep("SPD — 内存压缩（单项 feature）")
    print(f"本设备应检版本: {expected_label}")
    print(f"执行的检查: {check_executed}")
    all_rows = scope_rows + evidence_rows
    evr.print_check_result(feature_status, all_rows, extra_lines=detail_lines if not evidence_rows else None)

    if feature_status == "PASS":
        sys.exit(0)
    if feature_status == "FAIL":
        sys.exit(1)
    sys.exit(2)


if __name__ == "__main__":
    main()
