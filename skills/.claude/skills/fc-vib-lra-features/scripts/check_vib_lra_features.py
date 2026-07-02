#!/usr/bin/env python3
"""LRA vibration feature import - getprop check per feature_matrix."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here.parents[1] / "scripts"))
sys.path.insert(0, str(_here))

from adb_util import adb_shell, require_device  # noqa: E402
from feature_matrix import FEATURE_MATRIX  # noqa: E402

_ENABLED = frozenset({"true", "1"})
_NONEMPTY_PROPS = frozenset({"ro.tr_vibrate.notification_lra"})


def _short_prop(name: str) -> str:
    prefix = "ro.tr_vibrate."
    if name.startswith(prefix):
        rest = name[len(prefix) :]
        if rest.endswith(".feature.support"):
            return rest[: -len(".feature.support")]
        return rest
    return name.split(".")[-1]


def _getprop(name: str, adb: str | None) -> str:
    out, _ = adb_shell(f"getprop {name}", adb)
    return out.strip()


def _prop_ok(prop: str, value: str) -> bool:
    if prop in _NONEMPTY_PROPS:
        return bool(value.strip())
    return value.lower() in _ENABLED


def _collect_props(adb: str | None) -> dict[str, str]:
    names: set[str] = set()
    for row in FEATURE_MATRIX:
        for prop in row["props"]:  # type: ignore[index]
            names.add(str(prop))
    return {name: _getprop(name, adb) for name in sorted(names)}


def main() -> int:
    p = argparse.ArgumentParser(description="Check LRA vibration feature getprop imports")
    p.add_argument("--adb", default=None, help="adb executable path")
    args = p.parse_args()
    adb = args.adb

    require_device(adb)
    prop_values = _collect_props(adb)

    print("=== LRA 振动功能导入检查 ===\n")
    print("| 功能 | 轴向 | 所需属性 | 实际 | 结果 |")
    print("|------|------|----------|------|------|")

    pass_rows: list[str] = []
    fail_rows: list[str] = []
    for row in FEATURE_MATRIX:
        feature = str(row["feature"])
        axis = str(row["axis"])
        props: tuple[str, ...] = tuple(row["props"])  # type: ignore[arg-type]
        missing = [prop for prop in props if not _prop_ok(prop, prop_values.get(prop, ""))]
        ok = not missing
        required = ", ".join(_short_prop(prop) for prop in props)
        actual = ", ".join(
            f"{_short_prop(prop)}={prop_values.get(prop, '')!r}" for prop in props
        )
        status = "Pass" if ok else "Fail"
        print(f"| {feature} | {axis} | {required} | {actual} | {status} |")

        label = f"{feature} ({axis})"
        if ok:
            pass_rows.append(label)
        else:
            fail_rows.append(f"{label}（缺: {', '.join(missing)}）")

    print("\n=== 属性明细 ===\n")
    print("| 属性 | 实际 | 开启 |")
    print("|------|------|------|")
    for name, value in prop_values.items():
        en = "yes" if _prop_ok(name, value) else "no"
        print(f"| {name} | {value!r} | {en} |")

    print("\n=== 汇总 ===")
    print(f"- 已导入功能数: {len(pass_rows)}")
    print(f"- 未导入功能数: {len(fail_rows)}")

    if pass_rows:
        print("- 已导入:")
        for item in pass_rows:
            print(f"  - {item}")

    if fail_rows:
        print("- 未导入或不完整:")
        for item in fail_rows:
            print(f"  - {item}")

    print("RESULT: Pass - 导入检测完成（默认不要求表内功能全量导入）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
