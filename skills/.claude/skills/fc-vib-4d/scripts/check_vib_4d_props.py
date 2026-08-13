#!/usr/bin/env python3
"""4D game haptic feature getprop check — Windows/Linux."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from adb_util import adb_shell, require_device  # noqa: E402

# (prop, allowed values — empty string means unset/fail)
_CHECKS: list[tuple[str, frozenset[str]]] = [
    ("ro.tr_vibrate.vibrate10.feature.support", frozenset({"true"})),
    ("ro.tr_vibrate.vibrate20.feature.support", frozenset({"true"})),
    ("ro.tr_vibrate.vibrate30.feature.support", frozenset({"true"})),
    ("ro.tr_game.four_d_vibration.support", frozenset({"true", "1"})),
]


def _getprop(name: str, adb: str | None) -> str:
    out, _ = adb_shell(f"getprop {name}", adb)
    return out.strip()


def main() -> int:
    p = argparse.ArgumentParser(description="Check 4D haptic feature getprop flags")
    p.add_argument("--adb", default=None, help="adb executable path")
    args = p.parse_args()
    adb = args.adb

    require_device(adb)
    fail = False

    print("=== 4D haptic feature properties ===\n")
    print("| property | expected | actual | result |")
    print("|----------|----------|--------|--------|")

    for prop, allowed in _CHECKS:
        actual = _getprop(prop, adb)
        ok = actual in allowed
        expected = " or ".join(sorted(allowed))
        status = "Pass" if ok else "Fail"
        if not ok:
            fail = True
        print(f"| {prop} | {expected} | {actual!r} | {status} |")

    print()
    if fail:
        print("RESULT: Fail — not all 4D haptic properties are enabled.")
        return 1
    print("RESULT: Pass — all 4D haptic properties are enabled.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
