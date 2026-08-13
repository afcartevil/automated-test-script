#!/usr/bin/env python3
"""步骤 4 音量独立排查：仅需时间窗 + main/sys，不跑全量 game_power_parser。"""

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

from game_power_parser import discover_logs, extract_ts, fmt_time, iter_lines, parse_dt  # noqa: E402
from test_conditions_probe import probe_volume_stats  # noqa: E402


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景音量独立排查（步骤 4）")
    parser.add_argument("log_path", help="日志目录或 converted/APLog 目录")
    parser.add_argument("--start", required=True, help="T_start，YYYY-MM-DD HH:MM:SS 或 MM-DD HH:MM:SS")
    parser.add_argument("--end", required=True, help="T_end，格式同 --start")
    parser.add_argument("--pre-minutes", type=int, default=5, help="T_pre 分钟数")
    parser.add_argument("--music-stream", type=int, default=3, help="STREAM_MUSIC stream id，默认 3")
    parser.add_argument("--max-index", type=int, default=15, help="音量档位上限（用于百分比），默认 15")
    parser.add_argument(
        "--output",
        default="",
        help="输出 JSON 路径；默认 <log_path>/analysis/volume_probe.json",
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
    logs = discover_logs(log_path)
    volume_stats = probe_volume_stats(
        logs,
        start,
        end,
        pre_s,
        extract_ts,
        iter_lines,
        music_stream_id=args.music_stream,
        max_index=args.max_index,
    )

    notes: list[str] = []
    if not logs.get("main_log") and not logs.get("sys_log"):
        notes.append("main/sys 日志缺失，无法探测音量")
    elif volume_stats.get("coverage") == "missing":
        notes.append("T_pre/T_game 内未找到 STREAM_MUSIC 音量采样")
    elif volume_stats.get("coverage") == "partial":
        notes.append("T_game 内无音量变化采样，沿用 T_pre 基线")
    gw = volume_stats.get("game_window") or {}
    if gw.get("changed"):
        notes.append(f"T_game 音量 index 范围 {gw.get('index_min')}~{gw.get('index_max')}")
    elif gw.get("index_min") is not None:
        notes.append(f"T_game 音量恒定 index={gw.get('index_min')}")

    out: dict[str, Any] = {
        "skill": "flow_power_game",
        "probe": "volume",
        "step": 4,
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
        },
        "log_availability": {
            "main_log": bool(logs.get("main_log")),
            "sys_log": bool(logs.get("sys_log")),
        },
        "volume_stats": volume_stats,
        "notes": notes,
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
    }

    out_path = Path(args.output) if args.output else log_path / "analysis" / "volume_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
