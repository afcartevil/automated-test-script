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
from typing import Dict, List, Tuple


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


def check_props_memfusion(mf: Dict[str, str]) -> Tuple[bool, List[str]]:
    bad: List[str] = []
    if KEY_RSV2 not in mf or not prop_true(mf[KEY_RSV2]):
        bad.append(f"{KEY_RSV2} must exist and be true")
    if not prop_one(mf.get(KEY_RO_SUPPORT, "")):
        bad.append(f"{KEY_RO_SUPPORT} expected [1]")
    for k, label in ((KEY_V21, "version21"), (KEY_V22, "version22")):
        if not prop_true(mf.get(k, "")):
            bad.append(f"{k} ({label}) expected true")
    if not prop_true(mf.get(KEY_SWAP_SUP, "")):
        bad.append(f"{KEY_SWAP_SUP} expected true")
    if not swapfile_mb_ok(mf.get(KEY_SWAP_MB, "")):
        bad.append(f"{KEY_SWAP_MB} expected integer > 0")
    return len(bad) == 0, bad


def load_evidence_mem_compress_2_0() -> Tuple[Dict[str, str], str, str]:
    """Fetch getprop / dump_info / zram_bd_list for 2.0 checks (non-fatal adb rc)."""
    getprop_out = run_adb_shell("getprop", allow_nonzero=True)
    props = parse_props(getprop_out)
    mf = memfusion_subset(props)
    dump = run_adb_shell("cat /proc/memfusion/dump_info", allow_nonzero=True)
    zbl = run_adb_shell("cat /proc/memfusion/zram_bd_list", allow_nonzero=True)
    return mf, dump, zbl


def evaluate_mem_compress_2_0(mf: Dict[str, str], dump: str, zbl: str) -> Tuple[bool, List[str]]:
    """Return (pass, failure_messages) without printing or exiting."""
    failures: List[str] = []
    ok_p, prop_msgs = check_props_memfusion(mf)
    if not ok_p:
        failures.extend(prop_msgs)
    if not dump_swap_ok(dump):
        failures.append("dump_info: missing Swap_Write_Enable Kernel[On] Frameworks[On]")
    if not dump_has_zram0_partition(dump):
        failures.append("dump_info: expected zram0 + partition line")
    if not dump_has_swapfile_file(dump):
        failures.append("dump_info: expected swapfile + file line")
    if not zram_bd_list_has_dm(zbl):
        if zram_bd_list_only_loop_no_dm(zbl):
            failures.append("zram_bd_list: found loop backing but no /dev/block/dm-* (old path)")
        else:
            failures.append("zram_bd_list: no /dev/block/dm-* device path found")
    return len(failures) == 0, failures


def main() -> None:
    mf, dump, zbl = load_evidence_mem_compress_2_0()

    print("=== getprop (memfusion keys, excerpt) ===")
    for k in sorted(mf):
        print(f"[{k}]: [{mf[k]}]")

    print("\n=== cat /proc/memfusion/dump_info (excerpt) ===")
    d = dump.strip()
    print(d[:2500] + ("\n... (truncated)" if len(d) > 2500 else ""))

    print("\n=== cat /proc/memfusion/zram_bd_list ===")
    print(zbl.strip() or "(empty)")

    ok, failures = evaluate_mem_compress_2_0(mf, dump, zbl)
    if not ok:
        print("\n=== CHECK RESULT: FAIL ===")
        for msg in failures:
            print(f"- {msg}")
        sys.exit(1)

    print("\n=== CHECK RESULT: PASS ===")
    print("- memcgcprsv2.support=true and fusion memfusion props OK")
    print("- dump_info: zram0 partition + swapfile file + Swap_Write_Enable on")
    print("- zram_bd_list: device mapper dm-* present")
    sys.exit(0)


if __name__ == "__main__":
    main()
