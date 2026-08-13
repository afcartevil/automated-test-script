#!/usr/bin/env python3
"""LRA haptic owner check (system system) — Windows/Linux."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT.parent.parent / "scripts"))
sys.path.insert(0, str(_ROOT))

from adb_util import adb_shell, path_exists, require_device  # noqa: E402

from lra_nodes import (  # noqa: E402
    CHOWN_AND_MODE666_DEV,
    CHOWN_ONLY_DEV,
    VIBRATOR_LED_ATTRS,
    get_scheme,
    path_requires_mode666,
)


def parse_ls_line(line: str) -> tuple[str, str, str]:
    parts = line.split()
    if len(parts) < 4:
        return "-", "-", "-"
    return parts[0], parts[2], parts[3]


def check_owner(path: str, adb: str | None) -> tuple[bool, int]:
    """Returns (hard_fail, warn_count)."""
    if not path_exists(path, adb):
        print(f"{path:<58} {'no':<6} {'-':<16} MISSING")
        return False, 0

    out, _ = adb_shell(f"ls -l {path} 2>/dev/null", adb)
    line = out.split("\n")[0] if out else ""
    perm, owner, group = parse_ls_line(line)
    og = f"{owner}:{group}"
    warn = 0
    verdict = "OK"
    hard = False

    if owner != "system" or group != "system":
        verdict = "FAIL"
        hard = True
    elif path_requires_mode666(path) and len(perm) >= 10:
        if not (perm[1:4] == "rw-" and perm[4:7] == "rw-" and perm[7:10] == "rw-"):
            print(f"{path:<58} {'yes':<6} {og:<16} WARN-mode (mode {perm}, expect 666)")
            return False, 1

    print(f"{path:<58} {'yes':<6} {og:<16} {verdict}")
    if verdict == "OK" and perm != "-":
        print(f"       mode: {perm}")
    return hard, warn


def main() -> int:
    p = argparse.ArgumentParser(description="Check LRA node owner is system:system")
    p.add_argument("--adb", default=None, help="adb executable (default: adb or $ADB)")
    args = p.parse_args()
    adb = args.adb

    require_device(adb)
    fail = False
    checked = 0
    warn_total = 0

    leds_out, _ = adb_shell("ls /sys/class/leds/ 2>/dev/null", adb)
    scheme = get_scheme(leds_out)

    print(f"{'PATH':<58} {'EXISTS':<6} {'OWNER:GROUP':<16} VERDICT")
    print(f"{'----':<58} {'------':<6} {'-----------':<16} -------")

    if scheme.type == "none":
        print("scheme: none — no vibrator_single / vibrator_l / vibrator_r")
    else:
        print(f"scheme: {scheme.type} ({scheme.label}, full init.tp.rc list)")
        print("--- char dev ---")
        for path in CHOWN_ONLY_DEV + CHOWN_AND_MODE666_DEV:
            h, w = check_owner(path, adb)
            if path_exists(path, adb):
                checked += 1
            fail = fail or h
            warn_total += w

        for led in scheme.leds:
            print(f"--- sysfs {led} ---")
            for attr in VIBRATOR_LED_ATTRS:
                path = f"/sys/class/leds/{led}/{attr}"
                h, w = check_owner(path, adb)
                if path_exists(path, adb):
                    checked += 1
                fail = fail or h
                warn_total += w

    print()
    if path_exists("/odm/etc/init/init.tp.rc", adb):
        print("hint: /odm/etc/init/init.tp.rc present")
    else:
        print("hint: /odm/etc/init/init.tp.rc MISSING")

    print()
    if scheme.type == "none" or checked == 0:
        print("RESULT: Fail — no LRA led nodes found")
        return 1
    if fail:
        print("RESULT: Fail — fix chown in vib-adapt-haptic-rc / init.tp.rc")
        return 1
    if warn_total:
        print(f"RESULT: Pass (owner OK; {warn_total} mode WARN)")
        return 0
    print("RESULT: Pass — all checked nodes are system:system")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
