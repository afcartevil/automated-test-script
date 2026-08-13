#!/usr/bin/env python3
"""Factory midtest TP IC / firmware sysfs check — Windows/Linux."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from adb_util import adb_shell, path_exists, require_device  # noqa: E402

# Driver listing entries that are not device sysfs dirs.
_DRIVER_SKIP = frozenset({"bind", "unbind", "module", "uevent"})


def _add_base(bases: list[str], seen: set[str], base: str) -> None:
    base = base.rstrip("/")
    if base and base not in seen:
        seen.add(base)
        bases.append(base)


def _resolve_base(path: str, adb: str | None) -> str:
    rl, _ = adb_shell(f"readlink -f {path} 2>/dev/null", adb)
    return rl.strip() or path.rstrip("/")


def discover_sysfs_bases(adb: str | None) -> list[str]:
    """Collect directories that expose tp_vendor (deduped, resolved)."""
    bases: list[str] = []
    seen: set[str] = set()

    def add_dir(dir_path: str) -> None:
        dir_path = _resolve_base(dir_path, adb)
        if path_exists(f"{dir_path}/tp_vendor", adb):
            _add_base(bases, seen, dir_path)

    # 1. Canonical factory path: /sys/devices/platform/mtk-tpd[/2]
    for pdev in ("mtk-tpd", "mtk-tpd2"):
        add_dir(f"/sys/devices/platform/{pdev}")

    # 2. Driver bind dirs (e.g. .../mtk-tpd/odm:touch -> real pdev)
    drv_out, _ = adb_shell("ls /sys/bus/platform/drivers/mtk-tpd/ 2>/dev/null", adb)
    for name in drv_out.split():
        name = name.strip()
        if not name or name in _DRIVER_SKIP:
            continue
        add_dir(f"/sys/bus/platform/drivers/mtk-tpd/{name}")

    # 3. Fallback: platform tree (odm:touch etc. may be deeper than maxdepth 2)
    find_out, _ = adb_shell(
        "find /sys/devices/platform /sys/bus/platform/devices "
        "-maxdepth 5 -name tp_vendor 2>/dev/null",
        adb,
    )
    for vp in find_out.splitlines():
        vp = vp.strip()
        if vp.endswith("/tp_vendor"):
            add_dir(vp[: -len("/tp_vendor")])

    return bases


def main() -> int:
    p = argparse.ArgumentParser(description="Check factory TP vendor/firmware sysfs")
    p.add_argument("--adb", default=None)
    p.add_argument("--expect-vendor", default="", dest="expect_vendor")
    p.add_argument("--expect-fw", default="", dest="expect_fw")
    args = p.parse_args()
    adb = args.adb

    require_device(adb)
    fail = False

    print("=== TP factory info nodes ===")
    sysfs_bases = discover_sysfs_bases(adb)

    if not sysfs_bases:
        print("FAIL: no tp_vendor found (checked mtk-tpd, mtk-tpd2, drivers/mtk-tpd, platform find)")
        return 1

    rl, _ = adb_shell("readlink -f /sys/devices/platform/mtk-tpd 2>/dev/null", adb)
    if rl.strip():
        print(f"readlink mtk-tpd -> {rl.strip()}")

    for base in sysfs_bases:
        vendor, _ = adb_shell(f"cat {base}/tp_vendor 2>&1", adb)
        vendor = vendor.strip()
        fw, _ = adb_shell(f"cat {base}/tp_firmware_version 2>&1", adb)
        fw = fw.strip()[:200]
        fw_len = len(fw.encode("utf-8"))
        tname, _ = adb_shell(f"cat {base}/tp_name 2>/dev/null", adb)
        tname = tname.strip()

        v_ok = "OK"
        f_ok = "OK"

        if not vendor or vendor == "UNKNOWN":
            v_ok = "FAIL"
            fail = True
        elif "_" not in vendor:
            v_ok = "WARN-format"

        if fw_len == 0:
            f_ok = "FAIL-empty"
            fail = True
        elif not re.search(r"0x[0-9a-fA-F]+.*bv:", fw):
            f_ok = "WARN-format"
        elif re.search(r"0x0+[,_].*bv:0x0+", fw):
            f_ok = "FAIL-zeros"
            fail = True

        if args.expect_vendor and not re.search(
            re.escape(args.expect_vendor), vendor, re.I
        ):
            v_ok = "FAIL-expect"
            fail = True
        if args.expect_fw and not re.search(re.escape(args.expect_fw), fw, re.I):
            f_ok = "FAIL-expect"
            fail = True

        print(f"\nPATH: {base}")
        print(f"  tp_vendor: {vendor} [{v_ok}]")
        print(f"  tp_firmware_version ({fw_len} bytes): {fw or '<empty>'} [{f_ok}]")
        if tname:
            print(f"  tp_name: {tname}")

    print()
    if fail:
        print("RESULT: Fail — route tp-adapt-factory-sysfs / tp-adapt-engineering-sysfs")
        return 1
    print("RESULT: Pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
