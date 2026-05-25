#!/usr/bin/env python3
"""TP proc/sysfs SELinux check — Windows/Linux."""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from adb_util import adb_shell, path_exists, require_device  # noqa: E402

TP_PROC_NODES = [
    ("gesture_function", ["proc_gesture"]),
    ("gesture_state", ["proc_gesture"]),
    ("gesture_flag", ["proc_gesture"]),
    ("tp_panel_test", ["proc_nvt_selftest", "proc_main_selftest", "proc_nvt"]),
    ("fingerprint_status", ["proc_fingerprint"]),
    ("tp_large_area_mistouch_switch", ["proc_tp_large_area"]),
    ("tp_scene", ["proc_tp_scene"]),
]


def main() -> int:
    p = argparse.ArgumentParser(description="Check TP SELinux labels and shell read")
    p.add_argument("--adb", default=None)
    args = p.parse_args()
    adb = args.adb

    require_device(adb)
    fail = False

    print(f"{'NODE':<36} {'EXISTS':<8} {'LABEL':<40} {'READ':<12} MATCH")
    print(f"{'----':<36} {'------':<8} {'-----':<40} {'----':<12} -----")

    for node, frags in TP_PROC_NODES:
        path = f"/proc/{node}"
        exists = "no"
        label = "-"
        read_st = "-"
        match = "N/A"

        if path_exists(path, adb):
            exists = "yes"
            lz, _ = adb_shell(f"ls -Z {path} 2>/dev/null", adb)
            label = lz.split()[0] if lz.split() else "(unknown)"

            if re.search(r"unlabeled|default_t", label):
                match = "FAIL-label"
                fail = True
            elif any(f in label for f in frags):
                match = "OK"
            else:
                match = "WARN-type"

            out, _ = adb_shell(f"cat {path} 2>&1", adb)
            out = out[:80]
            low = out.lower()
            if "permission denied" in low:
                read_st = "DENIED"
                match = "FAIL-read"
                fail = True
            elif "no such file" in low:
                read_st = "MISSING"
                match = "FAIL-read"
                fail = True
            else:
                read_st = "OK"
        else:
            match = "MISSING"

        print(f"{path:<36} {exists:<8} {label:<40} {read_st:<12} {match}")

    print("\n--- sysfs mtk-tpd (sample) ---")
    sysfs_out, _ = adb_shell("ls -d /sys/bus/platform/drivers/mtk-tpd/*/ 2>/dev/null", adb)
    sysfs_base = next((ln.strip() for ln in sysfs_out.split("\n") if ln.strip()), "")
    if sysfs_base:
        for fname in ("tp_firmware_version", "tp_vendor"):
            sp = f"{sysfs_base}{fname}"
            if path_exists(sp, adb):
                lz, _ = adb_shell(f"ls -Z {sp} 2>/dev/null", adb)
                lbl = lz.split()[0] if lz.split() else "-"
                rc, _ = adb_shell(f"cat {sp} 2>&1", adb)
                rc = rc[:60]
                print(f"{sp} | label={lbl} | read={rc or 'empty'}")
                if "permission denied" in rc.lower():
                    fail = True
    else:
        print("mtk-tpd sysfs path not found (skip or check driver)")

    print()
    if fail:
        print("RESULT: Fail — route to tp-adapt-selinux")
        return 1
    print("RESULT: Pass (no hard failures on checked nodes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
