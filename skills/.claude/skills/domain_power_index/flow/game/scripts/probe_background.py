#!/usr/bin/env python3
"""步骤 2 后台行为独立排查（兼容层，推荐 game_background.py）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GB_SCRIPTS = _SCRIPT_DIR.parent / "game_background" / "scripts"
_GTW_SCRIPTS = _SCRIPT_DIR.parent / "game_time_window" / "scripts"

for p in (_GTW_SCRIPTS, _GAME_SCRIPTS, _GB_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_background_lib import analyze_game_background  # noqa: E402
from game_power_parser import (  # noqa: E402
    add_event,
    analyze_kernel_samples,
    discover_logs,
    extract_ts,
    fmt_time,
    iter_lines,
    load_baseline_cpu_cores,
    load_baseline_processes,
    parse_dt,
    parse_kernel,
    phase_for,
    window_for,
)


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景后台行为独立排查（步骤 2，兼容探针）")
    parser.add_argument("log_path")
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--game-package", default="", help="用于过滤游戏自身后台")
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--startup-seconds", type=int, default=60)
    parser.add_argument("--exit-seconds", type=int, default=30)
    parser.add_argument("--soc-model", default="")
    parser.add_argument("--link-cpu", action="store_true", help="解析 kernel 异常进程并交叉关联")
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

    abnormal_for_link: list[dict] | None = None
    if args.link_cpu:
        logs = discover_logs(log_path)
        abnormal_for_link = []
        if logs.get("kernel_log"):
            events: list[dict] = []
            pre_s = max(0, args.pre_minutes) * 60
            post_s = max(0, args.post_minutes) * 60
            kernel_summary = parse_kernel(
                logs["kernel_log"], events, start, end, pre_s, post_s
            )
            analysis = analyze_kernel_samples(
                kernel_summary.get("samples", []),
                args.game_package.strip(),
                load_baseline_processes(_SCRIPT_DIR),
                load_baseline_cpu_cores(_SCRIPT_DIR),
                args.soc_model.strip(),
                args.startup_seconds,
                args.exit_seconds,
                start,
                end,
            )
            abnormal_for_link = analysis.get("abnormal_processes", [])

    result = analyze_game_background(
        log_path,
        start,
        end,
        game_package=args.game_package.strip(),
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        startup_seconds=args.startup_seconds,
        exit_seconds=args.exit_seconds,
        link_kernel_cpu=abnormal_for_link is None,
        abnormal_processes=abnormal_for_link,
        discover_logs=discover_logs,
        extract_ts=extract_ts,
        window_for=window_for,
        iter_lines=iter_lines,
        fmt_time=fmt_time,
        add_event=add_event,
        phase_for=phase_for,
        load_baseline_processes=load_baseline_processes,
        scripts_dir=_SCRIPT_DIR,
    )

    out = {
        "skill": "flow_power_game",
        "probe": "background",
        "step": 2,
        "log_path": result.get("log_path"),
        "game_window": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
            "package": args.game_package.strip(),
            "source": "user_cli",
        },
        "log_availability": result.get("log_availability"),
        "top_background_packages": result.get("top_background_packages"),
        "background_stats": result.get("background_stats"),
        "misidentification": result.get("misidentification"),
        "abnormal_processes_linked": result.get("abnormal_processes_linked") or [],
        "notes": result.get("notes"),
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
    }

    out_path = Path(args.output) if args.output else log_path / "analysis" / "background_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
