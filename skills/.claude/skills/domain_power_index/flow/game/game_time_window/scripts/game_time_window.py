#!/usr/bin/env python3
"""游戏场景时间窗对齐 CLI：应用名、T_game、kernel/main/sys 覆盖检查。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"
for p in (_GAME_SCRIPTS, _SCRIPT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_log_paths import add_log_path_argument, resolve_log_path  # noqa: E402
from game_time_window_lib import analyze_time_window, parse_dt  # noqa: E402
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
        return Path(*parts[:idx]) / "analysis" / "game_time_window.json"
    return log_path / "analysis" / "game_time_window.json"


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景时间窗对齐（base_game_time_window）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--game-package", default="", help="游戏包名；无法自动识别时必填")
    parser.add_argument("--start", default="", help="T_start，YYYY-MM-DD HH:MM:SS 或 MM-DD HH:MM:SS")
    parser.add_argument("--end", default="", help="T_end，格式同 --start")
    parser.add_argument("--pre-minutes", type=int, default=5, help="T_pre 分钟数，默认 5")
    parser.add_argument("--post-minutes", type=int, default=3, help="T_post 分钟数，默认 3")
    parser.add_argument("--min-segment-seconds", type=int, default=120, help="忽略短于该秒数的游戏片段")
    parser.add_argument("--merge-gap-seconds", type=int, default=30, help="前台中断合并阈值（秒）")
    parser.add_argument("--startup-seconds", type=int, default=60, help="startup 阶段秒数")
    parser.add_argument("--exit-seconds", type=int, default=30, help="exit 阶段秒数")
    parser.add_argument("--output", default="", help="输出 JSON 路径")
    args = parser.parse_args(argv)
    debug_begin(args, "game_time_window", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    if not log_path.is_dir():
        print(f"日志目录不存在或不可读：{log_path}", file=sys.stderr)
        return 2

    start = parse_dt(args.start) if args.start else None
    end = parse_dt(args.end) if args.end else None
    if (args.start and not start) or (args.end and not end):
        print("无效的 --start / --end", file=sys.stderr)
        return 2
    if start and end and end <= start:
        print("结束时间必须晚于开始时间", file=sys.stderr)
        return 2

    result = analyze_time_window(
        log_path,
        game_package=args.game_package.strip() or None,
        start=start,
        end=end,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        min_segment_seconds=max(0, args.min_segment_seconds),
        merge_gap_seconds=max(0, args.merge_gap_seconds),
        startup_seconds=max(0, args.startup_seconds),
        exit_seconds=max(0, args.exit_seconds),
    )

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    gw = result.get("game_window", {})
    print(f"状态: {result.get('status')}")
    print(f"游戏: {result.get('game_name')} ({result.get('game_package')})")
    if gw.get("start") and gw.get("end"):
        print(f"时段: {gw['start']} ~ {gw['end']} ({gw.get('duration_seconds', 0)}s)")
    for key in ("kernel_log", "main_log", "sys_log"):
        cov = result.get("log_coverage", {}).get(key, {})
        print(f"{key}: {cov.get('status', 'missing')} covers_t_game={cov.get('covers_t_game')}")
    print(f"已写入: {out_path}")
    debug_end("game_time_window", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
