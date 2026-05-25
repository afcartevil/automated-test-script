#!/usr/bin/env python3
"""LRA haptic SELinux check — Windows/Linux."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
_VIB_ROOT = _ROOT.parent.parent / "fc-vib-rootperm" / "scripts"
sys.path.insert(0, str(_ROOT.parent.parent / "scripts"))
sys.path.insert(0, str(_VIB_ROOT))

from adb_util import adb_shell, path_exists, require_device  # noqa: E402

from lra_nodes import (  # noqa: E402
    CHOWN_AND_MODE666_DEV,
    CHOWN_ONLY_DEV,
    VIBRATOR_LED_ATTRS,
    get_scheme,
)


def test_label(path: str, do_read: bool, adb: str | None) -> bool:
    """Returns True if hard fail."""
    if not path_exists(path, adb):
        print(f"{path:<58} {'no':<5} {'-':<36} {'-':<6} MISSING")
        return False

    lz, _ = adb_shell(f"ls -Z {path} 2>/dev/null", adb)
    label = lz.split()[0] if lz.split() else "(unknown)"
    read_st = "skip"
    match = "OK"
    hard = False

    if "unlabeled" in label or "default_t" in label:
        match = "FAIL-label"
        hard = True
    if do_read:
        out, _ = adb_shell(f"cat {path} 2>&1", adb)
        out = out[:40]
        if "permission denied" in out.lower():
            read_st = "DENIED"
            match = "FAIL-read"
            hard = True
        else:
            read_st = "OK"

    print(f"{path:<58} {'yes':<5} {label:<36} {read_st:<6} {match}")
    return hard


def main() -> int:
    p = argparse.ArgumentParser(description="Check LRA SELinux labels")
    p.add_argument("--adb", default=None)
    args = p.parse_args()
    adb = args.adb

    require_device(adb)
    fail = False

    leds_out, _ = adb_shell("ls /sys/class/leds/ 2>/dev/null", adb)
    scheme = get_scheme(leds_out)

    print(f"{'PATH':<58} {'EXISTS':<5} {'LABEL':<36} {'READ':<6} MATCH")
    print(f"{'----':<58} {'------':<5} {'-----':<36} {'----':<6} -----")

    if scheme.type == "none":
        print("scheme: none")
    else:
        print(f"scheme: {scheme.type} ({scheme.label})")
        print("--- char dev ---")
        for path in CHOWN_ONLY_DEV + CHOWN_AND_MODE666_DEV:
            fail = test_label(path, False, adb) or fail

        for led in scheme.leds:
            print(f"--- {led} ---")
            for attr in VIBRATOR_LED_ATTRS:
                path = f"/sys/class/leds/{led}/{attr}"
                fail = test_label(path, attr == "rtp", adb) or fail

    print()
    if scheme.type == "none":
        print("RESULT: Fail — no LRA led nodes")
        return 1
    if fail:
        print("RESULT: Fail — sepolicy or fc-vib-rootperm")
        return 1
    print("RESULT: Pass")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
