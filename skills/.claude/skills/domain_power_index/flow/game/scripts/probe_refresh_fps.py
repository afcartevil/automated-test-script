#!/usr/bin/env python3
"""步骤 6 刷新率与帧率独立排查。"""

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

from game_power_parser import (  # noqa: E402
    add_event,
    discover_logs,
    extract_ts,
    fmt_time,
    iter_lines,
    parse_dt,
    window_for,
)
from refresh_fps_probe import probe_refresh_fps_stats  # noqa: E402


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景刷新率/帧率独立排查（步骤 6）")
    parser.add_argument("log_path")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--game-package", default="", help="用于主应用 BQP 图层匹配")
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--output", default="")
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
    stats = probe_refresh_fps_stats(
        logs,
        events,
        start,
        end,
        pre_s,
        post_s,
        args.game_package.strip(),
        extract_ts,
        iter_lines,
        window_for,
        add_event,
    )

    out = {
        "skill": "flow_power_game",
        "probe": "refresh_fps",
        "step": 6,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
            "package": args.game_package.strip(),
            "source": "user_cli",
        },
        "time_windows": {
            "T_pre": {"start": fmt_time(start - timedelta(seconds=pre_s)), "end": fmt_time(start)},
            "T_game": {"start": fmt_time(start), "end": fmt_time(end)},
            "T_post": {"start": fmt_time(end), "end": fmt_time(end + timedelta(seconds=post_s))},
        },
        "log_availability": {
            "main_log": bool(logs.get("main_log")),
            "sys_log": bool(logs.get("sys_log")),
            "events_log": bool(logs.get("events_log")),
        },
        "refresh_rate_stats": stats.get("refresh_rate_stats"),
        "frame_rate_stats": stats.get("frame_rate_stats"),
        "notes": stats.get("notes", []),
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
    }

    out_path = Path(args.output) if args.output else log_path / "analysis" / "refresh_fps_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
