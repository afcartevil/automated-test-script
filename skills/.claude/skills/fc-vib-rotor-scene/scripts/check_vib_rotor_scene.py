#!/usr/bin/env python3
"""Rotor ERM: three-level / scene haptic import — getprop check."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from adb_util import adb_shell, require_device  # noqa: E402

_OPTION_PROP = "ro.vendor.tran.vibrator.option"

_FEATURE_PROPS: tuple[str, ...] = (
    "ro.tr_vibrate.vibrate10.feature.support",
    "ro.tr_vibrate.vibrate20.feature.support",
    "ro.tr_vibrate.vibrate30.feature.support",
    "ro.vendor.tran.vibrator.algo",
    "ro.tr_vibrate.vibrate30_z.feature.support",
    "ro.tr_vibrate.realvib05.feature.support",
)

_DISABLED_VALUES = frozenset({"", "0", "false", "no", "off"})


def _getprop(name: str, adb: str | None) -> str:
    out, _ = adb_shell(f"getprop {name}", adb)
    return out.strip()


def _is_enabled(value: str) -> bool:
    return value.lower() not in _DISABLED_VALUES


def _option_item_ok(value: str) -> bool:
    """Pass when empty or non-single; Fail when 'single'."""
    return value.lower() != "single"


def _feature_item_ok(value: str) -> bool:
    """Pass when disabled/empty; Fail when enabled."""
    return not _is_enabled(value)


def _overall_fail(option_val: str, feature_vals: list[str]) -> bool:
    """Fail only when option is 'single' and all feature props are enabled."""
    if option_val.lower() != "single":
        return False
    return all(_is_enabled(v) for v in feature_vals)


def main() -> int:
    p = argparse.ArgumentParser(
        description="Check rotor ERM three-level / scene vibration import state"
    )
    p.add_argument("--adb", default=None, help="adb executable path")
    args = p.parse_args()
    adb = args.adb

    require_device(adb)

    print("=== 转子马达三档振动/场景震感导入检查 ===\n")
    print("| property | expected | actual | result |")
    print("|----------|----------|--------|--------|")

    option_val = _getprop(_OPTION_PROP, adb)
    print(
        f"| {_OPTION_PROP} | empty or not single | {option_val!r} | "
        f"{'Pass' if _option_item_ok(option_val) else 'Fail'} |"
    )

    feature_vals: list[str] = []
    for prop in _FEATURE_PROPS:
        actual = _getprop(prop, adb)
        feature_vals.append(actual)
        print(
            f"| {prop} | disabled/empty | {actual!r} | "
            f"{'Pass' if _feature_item_ok(actual) else 'Fail'} |"
        )

    fail = _overall_fail(option_val, feature_vals)
    print()
    if fail:
        print("RESULT: Fail — 导入状态：未导入或不完整（option=single 且 feature 全开）。")
        return 1
    print("RESULT: Pass — 导入状态：已导入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
