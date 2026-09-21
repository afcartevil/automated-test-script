#!/usr/bin/env python3
"""
SPD auto check: 内存压缩 2.0（新内存融合路径，说明图三项条件）。

1) 属性：`getprop | grep memfusion` 等价校验（脚本解析全量 getprop 中含 memfusion 的键）。
   - 必须存在且为 true：`persist.odm.tr_memfusion.memcgcprsv2.support`（内存压缩 2.0 标识）。
   - 须与融合侧一致：`ro.odm.tr_memfusion.support=1`，`version21/22=true`，`swapfile.support=true`，
     `swapfile_size_mb` 为大于 0 的整数。
   - **不**校验 `persist.odm.tr_memfusion.uxcompaction.support`（说明图明确可忽略）。

2) `cat /proc/memfusion/dump_info`：可读；含 **zram0** 与 **partition**；含 **swapfile** 与 **file**；
   且含 `Swap_Write_Enable:Kernel[On], Frameworks[On]`。

3) `cat /proc/memfusion/zram_bd_list`：须出现 **`/dev/block/dm-<n>`**（新路径 device mapper）；
   若仅见 **`/dev/block/loop`** 而无 dm，判为旧 backing，**FAIL**。

说明：内存压缩 2.0 为内存融合迭代；仍走压缩 1.1 软件路径，仅 ROM 框架为新；`aggr_enable` 等聚合回写
说明图注明可不再测，本脚本不测聚合回写。

图中具体机型/样例（如 Infinix-X6895B）不作为判定依据，仅以技术条件为准。
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


SWAP_DUMP_SNIPPET = "Swap_Write_Enable:Kernel[On], Frameworks[On]"
PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")

KEY_RSV2 = "persist.odm.tr_memfusion.memcgcprsv2.support"
KEY_RO_SUPPORT = "ro.odm.tr_memfusion.support"
KEY_V21 = "ro.odm.tr_memfusion.version21.support"
KEY_V22 = "ro.odm.tr_memfusion.version22.support"
KEY_SWAP_SUP = "persist.odm.tr_memfusion.swapfile.support"
KEY_SWAP_MB = "persist.odm.tr_memfusion.swapfile_size_mb"


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


def parse_props(raw: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for line in raw.splitlines():
        m = PROP_LINE_RE.match(line.strip())
        if m:
            props[m.group("key")] = m.group("value")
    return props


def memfusion_subset(props: Dict[str, str]) -> Dict[str, str]:
    return {k: v for k, v in props.items() if "memfusion" in k.lower()}


def dump_swap_ok(dump: str) -> bool:
    if not dump.strip():
        return False
    t = dump.replace(" ", "")
    needle = SWAP_DUMP_SNIPPET.replace(" ", "")
    return needle.lower() in t.lower()


def dump_has_zram0_partition(dump: str) -> bool:
    for line in dump.splitlines():
        lo = line.lower()
        if "zram0" in lo and "partition" in lo:
            return True
    return False


def dump_has_swapfile_file(dump: str) -> bool:
    for line in dump.splitlines():
        lo = line.lower()
        if "swapfile" in lo and "file" in lo:
            return True
    return False


def zram_bd_list_has_dm(raw: str) -> bool:
    return bool(re.search(r"/dev/block/dm-\d+", raw or ""))


def zram_bd_list_only_loop_no_dm(raw: str) -> bool:
    if zram_bd_list_has_dm(raw):
        return False
    return bool(re.search(r"/dev/block/loop\d+", raw or ""))


def prop_true(v: str) -> bool:
    return v.strip().lower() == "true"


def prop_one(v: str) -> bool:
    return v.strip() == "1"


def swapfile_mb_ok(v: str) -> bool:
    try:
        return int(v.strip()) > 0
    except ValueError:
        return False


def check_props_memfusion(
    mf: Dict[str, str],
    *,
    require_rsv2: bool = True,
) -> Tuple[bool, List[evr.EvidenceRow]]:
    """Fusion-side props for 2.0 path.

    ``memcgcprsv2`` 是 2.0 开关标识：专项脚本默认仍校验；
    「内存压缩状态」单版本入口只用它做应检路由，不再作为 PASS/FAIL 证据（require_rsv2=False）。
    """
    rows: List[evr.EvidenceRow] = []
    if require_rsv2:
        rows.append(
            evr.row(
                KEY_RSV2,
                "true",
                mf.get(KEY_RSV2),
                KEY_RSV2 in mf and prop_true(mf[KEY_RSV2]),
            )
        )
    rows.append(evr.row(KEY_RO_SUPPORT, "1", mf.get(KEY_RO_SUPPORT), prop_one(mf.get(KEY_RO_SUPPORT, ""))))
    for k, label in ((KEY_V21, "version21"), (KEY_V22, "version22")):
        rows.append(evr.row(f"{k} ({label})", "true", mf.get(k), prop_true(mf.get(k, ""))))
    rows.append(evr.row(KEY_SWAP_SUP, "true", mf.get(KEY_SWAP_SUP), prop_true(mf.get(KEY_SWAP_SUP, ""))))
    rows.append(
        evr.row(
            KEY_SWAP_MB,
            "整数 > 0",
            mf.get(KEY_SWAP_MB),
            swapfile_mb_ok(mf.get(KEY_SWAP_MB, "")),
        )
    )
    return all(r.ok for r in rows), rows


def load_evidence_mem_compress_2_0() -> Tuple[Dict[str, str], str, str]:
    """Fetch getprop / dump_info / zram_bd_list for 2.0 checks (non-fatal adb rc)."""
    getprop_out = run_adb_shell("getprop", allow_nonzero=True)
    props = parse_props(getprop_out)
    mf = memfusion_subset(props)
    dump = run_adb_shell("cat /proc/memfusion/dump_info", allow_nonzero=True)
    zbl = run_adb_shell("cat /proc/memfusion/zram_bd_list", allow_nonzero=True)
    return mf, dump, zbl


def evaluate_mem_compress_2_0(
    mf: Dict[str, str],
    dump: str,
    zbl: str,
    *,
    require_rsv2: bool = True,
) -> Tuple[bool, List[str]]:
    """Return (pass, failure_messages) without printing or exiting.

    Kept for status-router reuse; prefer ``evaluate_mem_compress_2_0_rows`` for self-check.
    """
    ok, rows = evaluate_mem_compress_2_0_rows(mf, dump, zbl, require_rsv2=require_rsv2)
    failures = [f"{r.name}: 预期={r.expected}, 实际={r.actual}" for r in rows if not r.ok]
    return ok, failures


def evaluate_mem_compress_2_0_rows(
    mf: Dict[str, str],
    dump: str,
    zbl: str,
    *,
    require_rsv2: bool = True,
) -> Tuple[bool, List[evr.EvidenceRow]]:
    """Return (pass, evidence rows) for expected-vs-actual reporting."""
    _ok_p, rows = check_props_memfusion(mf, require_rsv2=require_rsv2)

    dump_ok = dump_swap_ok(dump)
    rows.append(
        evr.row(
            "dump_info Swap_Write_Enable",
            SWAP_DUMP_SNIPPET,
            "命中" if dump_ok else ("(empty)" if not dump.strip() else "未命中 Kernel/Frameworks On"),
            dump_ok,
        )
    )
    zram_ok = dump_has_zram0_partition(dump)
    rows.append(
        evr.row(
            "dump_info zram0+partition",
            "含 zram0 且 partition",
            "命中" if zram_ok else "未命中",
            zram_ok,
        )
    )
    swap_ok = dump_has_swapfile_file(dump)
    rows.append(
        evr.row(
            "dump_info swapfile+file",
            "含 swapfile 且 file",
            "命中" if swap_ok else "未命中",
            swap_ok,
        )
    )

    dm_ok = zram_bd_list_has_dm(zbl)
    if dm_ok:
        actual_zbl = "含 /dev/block/dm-*"
    elif zram_bd_list_only_loop_no_dm(zbl):
        actual_zbl = "仅 loop、无 dm（旧路径）"
    elif not (zbl or "").strip():
        actual_zbl = "(empty)"
    else:
        actual_zbl = "无 /dev/block/dm-*"
    rows.append(evr.row("zram_bd_list", "含 /dev/block/dm-*", actual_zbl, dm_ok))

    return all(r.ok for r in rows), rows


def main(argv: List[str] | None = None) -> None:
    import argparse

    ap = argparse.ArgumentParser(description="SPD 内存压缩 2.0（新内存融合）三项检查")
    ap.add_argument(
        "--self-check-gate",
        action="store_true",
        help="自检用：非 2.0 应检范围时 exit 2（BLOCKED），避免非 2.0 机型误判 FAIL",
    )
    args = ap.parse_args(argv)

    mf, dump, zbl = load_evidence_mem_compress_2_0()

    if args.self_check_gate:
        # 与 check_mem_compress_status 应检逻辑对齐（lazy import 避免循环依赖）
        import check_mem_compress_status as st

        kernel_mm, uname = st.kernel_mm_soft()
        getprop_out = run_adb_shell("getprop", allow_nonzero=True)
        props = parse_props(getprop_out)
        if not kernel_mm:
            print("=== CHECK RESULT: BLOCKED ===")
            print("- 无法解析内核版本，无法判定是否属于内存压缩 2.0 应检范围")
            print(f"- uname -r: {uname or '(empty)'}")
            sys.exit(2)
        track, label, *_rest = st.resolve_expected_mem_compress(
            kernel_mm, mf, props, 0
        )
        if track != "2.0_new":
            print("=== CHECK RESULT: BLOCKED ===")
            print("- 本机不在「内存压缩 2.0」应检范围（前置条件不满足）")
            print(f"- 当前应检判定: {label} (track={track})")
            print("- 适用条件: memcgcprsv2.support=true，或 TOS≥16.3 且 kernel≥6.1")
            sys.exit(2)
        print(f"=== 适用范围: {label} ===\n")

    print("=== getprop (memfusion keys, excerpt) ===")
    for k in sorted(mf):
        print(f"[{k}]: [{mf[k]}]")

    print("\n=== cat /proc/memfusion/dump_info (excerpt) ===")
    d = dump.strip()
    print(d[:2500] + ("\n... (truncated)" if len(d) > 2500 else ""))

    print("\n=== cat /proc/memfusion/zram_bd_list ===")
    print(zbl.strip() or "(empty)")

    ok, rows = evaluate_mem_compress_2_0_rows(mf, dump, zbl)
    evr.print_check_result("PASS" if ok else "FAIL", rows)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
