#!/usr/bin/env python3
"""TP super-resolution ABS max check via adb getevent -p — Windows/Linux."""
from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from adb_util import adb_shell, require_device  # noqa: E402

_ABS_X = "0035"  # ABS_MT_POSITION_X
_ABS_Y = "0036"  # ABS_MT_POSITION_Y

_RE_DEVICE = re.compile(r"^add device \d+:\s+(/dev/input/event\d+)", re.M)
_RE_NAME = re.compile(r'^\s*name:\s+"(.*)"', re.M)
_RE_ABS_MAX = {
    _ABS_X: re.compile(
        rf"^\s*{_ABS_X}\s*:\s*value\s+\d+,\s*min\s+\d+,\s*max\s+(\d+)",
        re.M,
    ),
    _ABS_Y: re.compile(
        rf"^\s*{_ABS_Y}\s*:\s*value\s+\d+,\s*min\s+\d+,\s*max\s+(\d+)",
        re.M,
    ),
}

# TP 候选名称关键字（优先选用）
_TP_NAME_HINTS = (
    "mtk-tpd",
    "focaltech",
    "fts",
    "goodix",
    "chipone",
    "novatek",
    "ilitek",
    "omnivision",
    "touch",
)


@dataclass
class InputDevice:
    path: str
    name: str
    max_x: int
    max_y: int

    @property
    def score(self) -> int:
        """越高越像主 TP：名称命中 + 坐标上限大。"""
        s = self.max_x + self.max_y
        low = self.name.lower()
        if any(h in low for h in _TP_NAME_HINTS):
            s += 1_000_000
        return s


def _split_device_blocks(text: str) -> list[tuple[str, str]]:
    starts = [m.start() for m in _RE_DEVICE.finditer(text)]
    if not starts:
        return []
    blocks: list[tuple[str, str]] = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(text)
        block = text[start:end]
        m = _RE_DEVICE.search(block)
        if m:
            blocks.append((m.group(1), block))
    return blocks


def _parse_abs_max(block: str, code: str) -> int | None:
    m = _RE_ABS_MAX[code].search(block)
    return int(m.group(1)) if m else None


def discover_tp_devices(getevent_p: str) -> list[InputDevice]:
    devices: list[InputDevice] = []
    for path, block in _split_device_blocks(getevent_p):
        max_x = _parse_abs_max(block, _ABS_X)
        max_y = _parse_abs_max(block, _ABS_Y)
        if max_x is None or max_y is None:
            continue
        name_m = _RE_NAME.search(block)
        name = name_m.group(1) if name_m else ""
        devices.append(InputDevice(path=path, name=name, max_x=max_x, max_y=max_y))
    return devices


def pick_tp_device(devices: list[InputDevice]) -> InputDevice | None:
    if not devices:
        return None
    return max(devices, key=lambda d: d.score)


def _calc_expected(panel_w: int, panel_h: int, multiplier: int) -> tuple[int, int]:
    return panel_w * multiplier - 1, panel_h * multiplier - 1


def _infer_multiplier(max_val: int, panel: int) -> float:
    if panel <= 0:
        return 0.0
    return (max_val + 1) / panel


def main() -> int:
    p = argparse.ArgumentParser(
        description="Check TP super-resolution ABS max (0035/0036) from getevent -p"
    )
    p.add_argument("--adb", default=None, help="adb executable path")
    p.add_argument("--panel-w", type=int, default=0, help="panel width in pixels")
    p.add_argument("--panel-h", type=int, default=0, help="panel height in pixels")
    p.add_argument("--multiplier", type=int, default=0, help="super-resolution factor N")
    p.add_argument("--expect-max-x", type=int, default=0, dest="expect_max_x")
    p.add_argument("--expect-max-y", type=int, default=0, dest="expect_max_y")
    args = p.parse_args()
    adb = args.adb

    require_device(adb)
    out, code = adb_shell("getevent -p", adb)
    if code != 0 or not out:
        print("ERROR: adb shell getevent -p failed")
        return 1

    devices = discover_tp_devices(out)
    tp = pick_tp_device(devices)
    if tp is None:
        print("ERROR: no input device with ABS 0035/0036 (ABS_MT_POSITION_X/Y) found")
        print("Hint: run `adb shell getevent -p` manually and confirm TP event node")
        return 1

    print("=== TP super-resolution (getevent -p) ===\n")
    print(f"| field | value |")
    print(f"|-------|-------|")
    print(f"| event | {tp.path} |")
    print(f"| name | {tp.name} |")
    print(f"| ABS 0035 max (X) | {tp.max_x} |")
    print(f"| ABS 0036 max (Y) | {tp.max_y} |")
    print()

    expect_x = args.expect_max_x
    expect_y = args.expect_max_y
    if args.panel_w > 0 and args.panel_h > 0 and args.multiplier > 0:
        expect_x, expect_y = _calc_expected(args.panel_w, args.panel_h, args.multiplier)
        print(
            f"Expected (panel {args.panel_w}x{args.panel_h}, N={args.multiplier}): "
            f"max_x={expect_x}, max_y={expect_y}"
        )
        print(
            f"Formula: max = panel_resolution × N - 1 "
            f"→ X: {args.panel_w}×{args.multiplier}-1={expect_x}, "
            f"Y: {args.panel_h}×{args.multiplier}-1={expect_y}"
        )
        print()

    fail = False
    if expect_x > 0 and expect_y > 0:
        ok_x = tp.max_x == expect_x
        ok_y = tp.max_y == expect_y
        print("| check | expected | actual | result |")
        print("|-------|----------|--------|--------|")
        print(
            f"| ABS 0035 max | {expect_x} | {tp.max_x} | "
            f"{'Pass' if ok_x else 'Fail'} |"
        )
        print(
            f"| ABS 0036 max | {expect_y} | {tp.max_y} | "
            f"{'Pass' if ok_y else 'Fail'} |"
        )
        fail = not (ok_x and ok_y)
    else:
        # 快速判定：max 明显高于 1× 1080p 屏（未配 panel 时）
        quick_pass = tp.max_x > 1079 and tp.max_y > 2399
        print("Quick check (no --panel-w/--panel-h/--multiplier): ")
        print(f"  max_x > 1079 and max_y > 2399 → {'Pass' if quick_pass else 'Fail'}")
        if args.panel_w > 0:
            n_x = _infer_multiplier(tp.max_x, args.panel_w)
            print(f"  inferred N from panel_w={args.panel_w}: {n_x:.2f}")
        if args.panel_h > 0:
            n_y = _infer_multiplier(tp.max_y, args.panel_h)
            print(f"  inferred N from panel_h={args.panel_h}: {n_y:.2f}")
        fail = not quick_pass
        if fail:
            print(
                "\nTip: for strict check, pass e.g. "
                "--panel-w 1080 --panel-h 2400 --multiplier 16"
            )

    print()
    if fail:
        print("RESULT: Fail — super-resolution ABS max mismatch or not imported.")
        return 1
    print("RESULT: Pass — super-resolution ABS max looks correct.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
