#!/usr/bin/env python3
"""Touch Master (区域操作大师) import check — getprop only."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from adb_util import adb_shell, require_device  # noqa: E402

_PROP = "ro.tr_game.touch_master.model"

_MODEL_LABEL = {
    0: "未导入",
    1: "精简版",
    2: "全量版",
}


def _get_model(adb: str | None) -> tuple[int | None, str]:
    out, _ = adb_shell(f"getprop {_PROP}", adb)
    raw = out.strip()
    if not raw:
        return None, raw
    try:
        return int(raw), raw
    except ValueError:
        return None, raw


def main() -> int:
    p = argparse.ArgumentParser(description="Check Touch Master import (getprop)")
    p.add_argument("--adb", default=None, help="adb executable path")
    p.add_argument(
        "--expect-model",
        type=int,
        choices=(1, 2),
        default=0,
        help="strictly require model 1 or 2",
    )
    args = p.parse_args()
    adb = args.adb

    require_device(adb)

    model, raw = _get_model(adb)
    label = _MODEL_LABEL.get(model, "unknown") if model is not None else "unknown"

    print("=== Touch Master (区域操作大师) import ===\n")
    print("| field | value |")
    print("|-------|-------|")
    print(f"| property | {_PROP} |")
    print(f"| raw | {raw!r} |")
    print(f"| model | {model if model is not None else 'N/A'} |")
    print(f"| version | {label} |")
    print()

    prop_ok = model in (1, 2)
    if args.expect_model:
        prop_ok = model == args.expect_model
    expect_desc = str(args.expect_model) if args.expect_model else "1 或 2"

    print("| check | expected | actual | result |")
    print("|-------|----------|--------|--------|")
    prop_status = "Pass" if prop_ok else "Fail"
    print(f"| {_PROP} | {expect_desc} | {raw!r} | {prop_status} |")
    print()

    if not prop_ok:
        print("RESULT: Fail — Touch Master property not enabled.")
        return 1
    print("RESULT: Pass — Touch Master property looks imported.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
