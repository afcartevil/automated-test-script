#!/usr/bin/env python3
"""步骤 3 亮度独立排查：仅需时间窗 + kernel/main/sys，不跑全量 game_power_parser。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from display_brightness import parse_hwcomposer_brightness, parse_kernel_backlight  # noqa: E402
from game_power_parser import (  # noqa: E402
    add_event,
    discover_logs,
    extract_ts,
    fmt_time,
    iter_lines,
    parse_dt,
    window_for,
)


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景亮度独立排查（步骤 3）")
    parser.add_argument("log_path", help="日志目录或 converted/APLog 目录")
    parser.add_argument("--start", required=True, help="T_start，YYYY-MM-DD HH:MM:SS 或 MM-DD HH:MM:SS")
    parser.add_argument("--end", required=True, help="T_end，格式同 --start")
    parser.add_argument("--pre-minutes", type=int, default=5, help="T_pre 分钟数")
    parser.add_argument("--post-minutes", type=int, default=3, help="T_post 分钟数")
    parser.add_argument(
        "--output",
        default="",
        help="输出 JSON 路径；默认 <log_path>/analysis/display_brightness_probe.json",
    )
    args = parser.parse_args(argv)

    log_path = Path(args.log_path).resolve()
    if not log_path.is_dir():
        print(f"日志目录不存在：{log_path}", file=sys.stderr)
        return 2

    start = parse_dt(args.start)
    end = parse_dt(args.end)
    if not start or not end or end <= start:
        print("无效的 --start / --end", file=sys.stderr)
        return 2

    pre_s = max(0, args.pre_minutes) * 60
    post_s = max(0, args.post_minutes) * 60
    logs = discover_logs(log_path)
    events: list[dict[str, Any]] = []

    lcm = parse_kernel_backlight(
        logs.get("kernel_log", []),
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        fmt_time,
        start,
        end,
        pre_s,
        post_s,
    )
    hwc = parse_hwcomposer_brightness(
        logs.get("main_log", []) + logs.get("sys_log", []),
        events,
        add_event,
        extract_ts,
        window_for,
        iter_lines,
        start,
        end,
        pre_s,
        post_s,
    )

    out = {
        "skill": "flow_power_game",
        "probe": "display_brightness",
        "step": 3,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
            "source": "user_cli",
        },
        "time_windows": {
            "T_pre": {"start": fmt_time(start - timedelta(seconds=pre_s)), "end": fmt_time(start)},
            "T_game": {"start": fmt_time(start), "end": fmt_time(end)},
            "T_post": {"start": fmt_time(end), "end": fmt_time(end + timedelta(seconds=post_s))},
        },
        "log_availability": {
            "kernel_log": bool(logs.get("kernel_log")),
            "main_log": bool(logs.get("main_log")),
            "sys_log": bool(logs.get("sys_log")),
        },
        "brightness_stats": {
            **lcm,
            "hwcomposer": hwc,
        },
        "notes": list(lcm.get("notes", [])) + list(hwc.get("notes", [])),
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
    }

    out_path = Path(args.output) if args.output else log_path / "analysis" / "display_brightness_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
