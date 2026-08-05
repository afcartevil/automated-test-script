#!/usr/bin/env python3
"""游戏场景音量 CLI（STREAM_MUSIC 基线 + 游戏内变音量）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"
_GTW_SCRIPTS = _SCRIPT_DIR.parent.parent / "game_time_window" / "scripts"

for p in (_SCRIPT_DIR, _GAME_SCRIPTS, _GTW_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_log_paths import (  # noqa: E402
    WINDOW_JSON_HELP,
    add_log_path_argument,
    resolve_log_path,
    resolve_window_json_path,
)
from game_power_parser import discover_logs, extract_ts, fmt_time, iter_lines, parse_dt  # noqa: E402
from game_time_window_lib import window_for  # noqa: E402
from game_volume_lib import analyze_game_volume  # noqa: E402
from game_skill_debug import (  # noqa: E402
    add_debug_log_arguments,
    debug_begin,
    debug_end,
)


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def default_output_path(log_path: Path) -> Path:
    parts = list(log_path.resolve().parts)
    lower = [p.lower() for p in parts]
    if "converted" in lower:
        idx = lower.index("converted")
        return Path(*parts[:idx]) / "analysis" / "game_volume.json"
    return log_path / "analysis" / "game_volume.json"


def _load_window_from_json(path: Path) -> tuple[datetime | None, datetime | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    return parse_dt(gw.get("start")), parse_dt(gw.get("end"))


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景音量分析（game_volume）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="", help="T_start；可省略若提供 --window-json")
    parser.add_argument("--end", default="", help="T_end；可省略若提供 --window-json")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--music-stream", type=int, default=3, help="STREAM_MUSIC stream id，默认 3")
    parser.add_argument("--max-index", type=int, default=15, help="音量档位上限（百分比），默认 15")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_volume", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    if not log_path.is_dir():
        print(f"日志目录不存在：{log_path}", file=sys.stderr)
        return 2

    start = parse_dt(args.start) if args.start else None
    end = parse_dt(args.end) if args.end else None
    wpath = resolve_window_json_path(log_path, args.window_json or None)
    if wpath.is_file():
            w_start, w_end = _load_window_from_json(wpath)
            start = start or w_start
            end = end or w_end
    if not start or not end or end <= start:
        print("无效时间窗：请提供 --start/--end 或有效 --window-json", file=sys.stderr)
        return 2

    result = analyze_game_volume(
        log_path,
        start,
        end,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        music_stream_id=args.music_stream,
        max_index=args.max_index,
        discover_logs=discover_logs,
        extract_ts=extract_ts,
        window_for=window_for,
        iter_lines=iter_lines,
        fmt_time=fmt_time,
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_volume"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    pre = result.get("pre_test_volume") or {}
    ing = result.get("in_game_volume") or {}
    inv = result.get("volume_investigation") or {}
    s1 = inv.get("step1_test_setting") or {}
    s2 = inv.get("step2_in_game_changes") or {}
    base = pre.get("baseline") or {}
    if s1.get("volume") is not None:
        dev = s1.get("device_label") or s1.get("device")
        adj = s1.get("adjustment_method") or ""
        print(
            f"步骤1 测试音量: {s1['volume']}/15 "
            f"device={dev} {f'({adj})' if adj else ''}"
        )
    if s2:
        changed = "有变化" if s2.get("changed") else "无变化"
        print(
            f"步骤2 游戏内音量: {changed} "
            f"range={s2.get('volume_min')}~{s2.get('volume_max')} "
            f"key_press={s2.get('key_press_adjustments', 0)}"
        )
    print(f"状态: {result.get('status')}")
    print(f"测试前音量: index={base.get('index')} ({base.get('index_pct')}%)")
    print(
        f"T_game 音量: min={ing.get('index_min')} max={ing.get('index_max')} "
        f"stable={ing.get('stable')} transitions={len(ing.get('transitions') or [])}"
    )
    print(f"已写入: {out_path}")
    debug_end("game_volume", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
