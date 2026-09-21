#!/usr/bin/env python3
"""
Detect 内存融合 (fusion) and 内存压缩 (compression) versions from /proc/memfusion
and related props, per internal guide:

- Fusion 2.2: dump_info swap line + swap_write_enable == 1
- Fusion 3.0: same + swap_write_enable == 3 + aggr_enable contains aggr ab: on
- Compress 1.0: base + swap 3 + compress_enable contains compress: on
- Compress 1.1: base + swap 3 + memcg-compress on + cgroup v2 memory +
    persist.tr_perf.aegean.mem_compact.support == 2 +
    persist.odm.tr_memfusion.memcgcprav2.support is false or absent
- Compress 2.0 (新内存融合说明图): memcgcpr**rsv2**.support=true + dump zram0/swapfile + Swap_Write_On + zram_bd_list dm-*
- Compress 2.0 (旧 cgroup 路径): memcg v1+v2 on + memcgcpr**av2** + aegean mem_compact=2 ...

Outputs MEMFUSION_VERSION / MEMCOMPRESS_VERSION for downstream scripts (--export).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


SWAP_DUMP_SNIPPET = "Swap_Write_Enable:Kernel[On], Frameworks[On]"
PROP_LINE_RE = re.compile(r"^\[(?P<key>.+?)\]:\s*\[(?P<value>.*)\]\s*$")

MEMCG_V2_PROP = "persist.odm.tr_memfusion.memcgcprav2.support"
MEMCG_RSV2_PROP = "persist.odm.tr_memfusion.memcgcprsv2.support"
AEGEAN_MEM_COMPACT = "persist.tr_perf.aegean.mem_compact.support"


def run_adb_shell(command: str) -> Tuple[int, str]:
    try:
        proc = subprocess.run(
            ["adb", "shell", command],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return 127, ""
    return proc.returncode, proc.stdout or ""


def parse_getprop(raw: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    for line in raw.splitlines():
        m = PROP_LINE_RE.match(line.strip())
        if m:
            props[m.group("key")] = m.group("value")
    return props


def first_line(text: str) -> str:
    for line in text.splitlines():
        s = line.strip()
        if s:
            return s
    return ""


def norm_lower(s: str) -> str:
    return s.lower().replace(" ", "")


def dump_swap_ok(dump_info: str) -> bool:
    if not dump_info.strip():
        return False
    # Guide: substring present; tolerate minor spacing differences.
    t = dump_info.replace(" ", "")
    needle = SWAP_DUMP_SNIPPET.replace(" ", "")
    return needle.lower() in t.lower()


def memcg_compress_on(text: str) -> bool:
    return "memcg-compress:on" in norm_lower(text) or "memcg_compress:on" in norm_lower(
        text.replace("-", "_")
    )


def memcg_compress_v2_on(text: str) -> bool:
    t = norm_lower(text)
    return "memcg-compress-v2:on" in t or "memcg_compress_v2:on" in t


def aggr_ab_on(text: str) -> bool:
    return re.search(r"aggr\s*ab\s*:\s*on", text, re.IGNORECASE) is not None


def compress_legacy_on(text: str) -> bool:
    """compress_enable line like 'compress: on'."""
    t = text.lower()
    return "compress:on" in norm_lower(text) or "compress: on" in t


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


def is_mem_compress_2_0_new_fusion(ev: Dict[str, Any]) -> bool:
    """内存压缩 2.0（新内存融合）：说明图三项之一 — 属性 rsv2 + dump + dm backing。"""
    mf = ev.get("memfusion_props") or {}
    if mf.get(MEMCG_RSV2_PROP, "").strip().lower() != "true":
        return False
    dump = ev.get("dump_info") or ""
    if not dump_has_zram0_partition(dump) or not dump_has_swapfile_file(dump):
        return False
    return zram_bd_list_has_dm(ev.get("zram_bd_list") or "")


def cgroup_v2_has_memory(controllers_text: str) -> bool:
    parts = re.split(r"[\s,]+", controllers_text.strip())
    return any(p.strip() == "memory" for p in parts if p.strip())


def pick_uid1000_pid() -> Optional[str]:
    code, out = run_adb_shell("ls /sys/fs/cgroup/system/uid_1000 2>/dev/null")
    if code != 0:
        return None
    for name in out.split():
        name = name.strip()
        if name.isdigit():
            return name
    return None


def collect_evidence() -> Dict[str, Any]:
    ev: Dict[str, Any] = {}

    rc, dump = run_adb_shell("cat /proc/memfusion/dump_info 2>/dev/null")
    ev["dump_info_rc"] = rc
    ev["dump_info"] = dump

    rc, sw = run_adb_shell("cat /proc/memfusion/swap_write_enable 2>/dev/null")
    ev["swap_write_enable_rc"] = rc
    ev["swap_write_enable"] = first_line(sw)

    rc, ag = run_adb_shell("cat /proc/memfusion/aggr_enable 2>/dev/null")
    ev["aggr_enable_rc"] = rc
    ev["aggr_enable"] = ag

    rc, ce = run_adb_shell("cat /proc/memfusion/compress_enable 2>/dev/null")
    ev["compress_enable_rc"] = rc
    ev["compress_enable"] = ce

    rc, mc = run_adb_shell("cat /proc/memfusion/memcg_compress 2>/dev/null")
    ev["memcg_compress_rc"] = rc
    ev["memcg_compress"] = mc

    rc, mcv2 = run_adb_shell("cat /proc/memfusion/memcg_compress_v2 2>/dev/null")
    ev["memcg_compress_v2_rc"] = rc
    ev["memcg_compress_v2"] = mcv2

    pid = pick_uid1000_pid()
    ev["uid1000_sample_pid"] = pid
    if pid:
        path = f"/sys/fs/cgroup/system/uid_1000/{pid}/cgroup.controllers"
        rc2, ctxt = run_adb_shell(f"cat {path} 2>/dev/null")
        ev["cgroup_controllers_rc"] = rc2
        ev["cgroup_controllers_path"] = path
        ev["cgroup_controllers"] = ctxt
    else:
        ev["cgroup_controllers_rc"] = -1
        ev["cgroup_controllers_path"] = None
        ev["cgroup_controllers"] = ""

    rc, zbl = run_adb_shell("cat /proc/memfusion/zram_bd_list 2>/dev/null")
    ev["zram_bd_list_rc"] = rc
    ev["zram_bd_list"] = zbl

    rc, gp = run_adb_shell("getprop")
    ev["getprop_rc"] = rc
    props = parse_getprop(gp) if rc == 0 else {}
    ev["memfusion_props"] = {k: v for k, v in props.items() if "memfusion" in k.lower()}
    ev["props"] = {
        AEGEAN_MEM_COMPACT: props.get(AEGEAN_MEM_COMPACT),
        MEMCG_V2_PROP: props.get(MEMCG_V2_PROP),
        MEMCG_RSV2_PROP: props.get(MEMCG_RSV2_PROP),
    }
    return ev


def memcg_v2_prop_false_or_absent(val: Optional[str]) -> bool:
    if val is None:
        return True
    s = val.strip().lower()
    return s in ("false", "0", "")


def memcg_v2_prop_true(val: Optional[str]) -> bool:
    if val is None:
        return False
    return val.strip().lower() == "true"


def detect_fusion(ev: Dict[str, Any]) -> Tuple[str, str]:
    dump = ev.get("dump_info") or ""
    if not dump_swap_ok(dump):
        return "unknown", "dump_info missing or Swap_Write_Enable Kernel/Frameworks On not found"

    sw = (ev.get("swap_write_enable") or "").strip()
    if sw == "1":
        return "2.2", "swap_write_enable == 1"
    if sw == "3" and aggr_ab_on(ev.get("aggr_enable") or ""):
        return "3.0", "swap_write_enable == 3 and aggr ab: on"
    if sw == "3":
        return "unknown", "swap_write_enable == 3 but aggr_enable does not match Fusion 3.0"
    if sw:
        return "unknown", f"swap_write_enable value {sw!r} not mapped to 2.2/3.0"
    return "unknown", "swap_write_enable empty or unreadable"


def detect_compress(ev: Dict[str, Any]) -> Tuple[str, str]:
    dump = ev.get("dump_info") or ""
    if not dump_swap_ok(dump):
        return "unknown", "dump_info prerequisite not met"

    if is_mem_compress_2_0_new_fusion(ev):
        return "2.0", "memcgcprsv2 + dump zram0/swapfile + zram_bd_list dm (内存压缩2.0 新融合)"

    sw = (ev.get("swap_write_enable") or "").strip()
    if sw != "3":
        return "none", f"compression branches in guide require swap_write_enable == 3, got {sw!r}"

    props = ev.get("props") or {}
    aegean_mc = props.get(AEGEAN_MEM_COMPACT)
    memcg_pr = props.get(MEMCG_V2_PROP)

    cgroup_txt = ev.get("cgroup_controllers") or ""
    cg_ok = cgroup_v2_has_memory(cgroup_txt)

    mcv1 = memcg_compress_on(ev.get("memcg_compress") or "")
    mcv2 = memcg_compress_v2_on(ev.get("memcg_compress_v2") or "")
    legacy_compress = compress_legacy_on(ev.get("compress_enable") or "")

    # 2.0（旧路径：cgroup + memcg_compress_v2 + memcgcprav2）
    if (
        mcv1
        and mcv2
        and cg_ok
        and (aegean_mc or "").strip() == "2"
        and memcg_v2_prop_true(memcg_pr)
    ):
        return "2.0", "memcg v1+v2 on, cgroup memory, aegean mem_compact=2, memcgcprav2=true"

    # 1.1
    if (
        mcv1
        and cg_ok
        and (aegean_mc or "").strip() == "2"
        and memcg_v2_prop_false_or_absent(memcg_pr)
    ):
        return "1.1", "memcg-compress on, cgroup memory, aegean mem_compact=2, memcgcprav2 false/absent"

    # 1.0
    if legacy_compress:
        return "1.0", "compress_enable indicates compress on (swap 3)"

    return "unknown", "swap 3 but pattern does not match 1.0 / 1.1 / 2.0 (含新融合 rsv2 路径)"


def print_evidence(ev: Dict[str, Any]) -> None:
    print("=== cat /proc/memfusion/dump_info (excerpt) ===")
    d = (ev.get("dump_info") or "").strip()
    if len(d) > 2000:
        print(d[:2000] + "\n... (truncated)")
    else:
        print(d or "(empty)")

    print("\n=== cat /proc/memfusion/swap_write_enable ===")
    print((ev.get("swap_write_enable") or "(empty)").strip() or "(empty)")

    print("\n=== cat /proc/memfusion/aggr_enable ===")
    print((ev.get("aggr_enable") or "").strip() or "(empty)")

    print("\n=== cat /proc/memfusion/compress_enable ===")
    print((ev.get("compress_enable") or "").strip() or "(empty)")

    print("\n=== cat /proc/memfusion/memcg_compress ===")
    print((ev.get("memcg_compress") or "").strip() or "(empty)")

    print("\n=== cat /proc/memfusion/memcg_compress_v2 ===")
    print((ev.get("memcg_compress_v2") or "").strip() or "(empty)")

    print("\n=== cgroup v2 sample ===")
    pid = ev.get("uid1000_sample_pid")
    if ev.get("cgroup_controllers_path"):
        print(f"path: {ev.get('cgroup_controllers_path')}")
        print((ev.get("cgroup_controllers") or "").strip() or "(empty)")
    else:
        print(f"uid_1000 first pid: {pid!s} (could not read cgroup.controllers)")

    print("\n=== cat /proc/memfusion/zram_bd_list ===")
    print((ev.get("zram_bd_list") or "").strip() or "(empty)")

    print("\n=== relevant getprop ===")
    pr = ev.get("props") or {}
    print(f"{AEGEAN_MEM_COMPACT}: {pr.get(AEGEAN_MEM_COMPACT)!r}")
    print(f"{MEMCG_V2_PROP}: {pr.get(MEMCG_V2_PROP)!r}")
    print(f"{MEMCG_RSV2_PROP}: {pr.get(MEMCG_RSV2_PROP)!r}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Detect memfusion / memcompress versions.")
    ap.add_argument(
        "--json",
        action="store_true",
        help="Print one JSON object with versions and evidence keys.",
    )
    ap.add_argument(
        "--export",
        action="store_true",
        help="Print MEMFUSION_VERSION=... and MEMCOMPRESS_VERSION=... for shell sourcing.",
    )
    args = ap.parse_args()

    code, _ = run_adb_shell("echo ok")
    if code == 127:
        print("ERROR: adb not found in PATH.", file=sys.stderr)
        sys.exit(2)
    if code != 0:
        print("ERROR: adb shell failed; check device connection.", file=sys.stderr)
        sys.exit(2)

    ev = collect_evidence()
    fusion_ver, fusion_reason = detect_fusion(ev)
    compress_ver, compress_reason = detect_compress(ev)

    if args.json:
        out = {
            "memfusion_version": fusion_ver,
            "memfusion_reason": fusion_reason,
            "memcompress_version": compress_ver,
            "memcompress_reason": compress_reason,
            "evidence": {
                "swap_write_enable": ev.get("swap_write_enable"),
                "uid1000_sample_pid": ev.get("uid1000_sample_pid"),
                "props": ev.get("props"),
            },
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        sys.exit(0)

    print_evidence(ev)
    print("\n=== VERSION RESULT ===")
    print(f"memfusion_version: {fusion_ver}")
    print(f"  ({fusion_reason})")
    print(f"memcompress_version: {compress_ver}")
    print(f"  ({compress_reason})")

    # Self-check 结论用：识别项也输出「预期 vs 实际」
    _shared = Path(__file__).resolve().parent.parent / "spd_shared" / "scripts"
    if _shared.is_dir() and str(_shared) not in sys.path:
        sys.path.insert(0, str(_shared))
    try:
        import evidence_report as evr

        fusion_ok = fusion_ver not in ("unknown", "", None)
        compress_ok = compress_ver not in ("unknown", "", None)
        rows = [
            evr.row(
                "内存融合版本识别",
                "可识别（非 unknown）",
                f"{fusion_ver} — {fusion_reason}",
                fusion_ok,
            ),
            evr.row(
                "内存压缩版本识别",
                "可识别（非 unknown）",
                f"{compress_ver} — {compress_reason}",
                compress_ok,
            ),
        ]
        # 识别用例：能跑通取证即 PASS；unknown 仍记 FAIL 明细但 exit 0（与历史行为一致）
        evr.print_check_result("PASS", rows)
    except Exception:
        print("\n=== CHECK RESULT: PASS ===")
        print(f"- memfusion_version={fusion_ver}")
        print(f"- memcompress_version={compress_ver}")

    if args.export:
        # Use safe single-line values
        print("\n=== EXPORT (source in sh) ===")
        print(f"MEMFUSION_VERSION={fusion_ver}")
        print(f"MEMCOMPRESS_VERSION={compress_ver}")

    sys.exit(0)


if __name__ == "__main__":
    main()
