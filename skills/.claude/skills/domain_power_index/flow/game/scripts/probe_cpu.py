#!/usr/bin/env python3
"""步骤 1 CPU/线程独立排查：仅需时间窗 + kernel（linli 优先），不跑全量 game_power_parser。"""

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
    analyze_kernel_samples,
    discover_logs,
    fmt_time,
    load_baseline_cpu_cores,
    load_baseline_processes,
    parse_dt,
    parse_kernel,
    serialize_cpu_samples,
)


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景 CPU/线程独立排查（步骤 1）")
    parser.add_argument("log_path", help="日志目录或 converted/APLog 目录")
    parser.add_argument("--start", required=True, help="T_start，YYYY-MM-DD HH:MM:SS 或 MM-DD HH:MM:SS")
    parser.add_argument("--end", required=True, help="T_end，格式同 --start")
    parser.add_argument("--game-package", default="", help="游戏包名，用于异常进程白名单判定")
    parser.add_argument("--soc-model", default="", help="SoC 型号，匹配 baseline-cpu-cores 平台标准")
    parser.add_argument("--pre-minutes", type=int, default=5, help="T_pre 分钟数")
    parser.add_argument("--post-minutes", type=int, default=3, help="T_post 分钟数")
    parser.add_argument("--startup-seconds", type=int, default=60, help="T_game 启动阶段秒数")
    parser.add_argument("--exit-seconds", type=int, default=30, help="T_game 退出阶段秒数")
    parser.add_argument(
        "--output",
        default="",
        help="输出 JSON 路径；默认 <log_path>/analysis/cpu_probe.json",
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

    kernel_summary = parse_kernel(
        logs.get("kernel_log", []),
        events,
        start,
        end,
        pre_s,
        post_s,
    )
    script_dir = _SCRIPT_DIR
    analysis = analyze_kernel_samples(
        kernel_summary.get("samples", []),
        args.game_package.strip(),
        load_baseline_processes(script_dir),
        load_baseline_cpu_cores(script_dir),
        args.soc_model.strip(),
        args.startup_seconds,
        args.exit_seconds,
        start,
        end,
    )
    kernel_summary.update(analysis)

    cpu_samples = serialize_cpu_samples(
        kernel_summary.get("samples", []),
        start,
        end,
        args.startup_seconds,
        args.exit_seconds,
    )
    game_samples = [s for s in cpu_samples if s.get("window") == "T_game"]
    stable_samples = [s for s in game_samples if s.get("phase") == "stable"]

    notes: list[str] = list(kernel_summary.get("baseline_process_notes", []))
    if not logs.get("kernel_log"):
        notes.insert(0, "kernel 日志缺失，AP/CPU 证据不足")
    elif kernel_summary.get("sample_count", 0) == 0:
        notes.insert(0, "T_pre/T_game 内无 [K][Perf] 采样")
    else:
        notes.append(
            f"[K] 采样 {kernel_summary.get('sample_count')} 轮；"
            f"T_game {len(game_samples)} 轮，stable {len(stable_samples)} 轮"
        )
    abnormal = kernel_summary.get("abnormal_processes") or []
    if abnormal:
        top = abnormal[0]
        notes.append(
            f"异常进程 Top: {top.get('name')} 出现 {top.get('occurrence_count')}/"
            f"{top.get('total_samples')} 轮"
        )
    core_stats = kernel_summary.get("cpu_core_usage_stats") or {}
    if core_stats.get("abnormal_core_count"):
        notes.append(f"可疑/异常 CPU 核数: {core_stats['abnormal_core_count']}")

    out: dict[str, Any] = {
        "skill": "flow_power_game",
        "probe": "cpu",
        "step": 1,
        "log_path": str(log_path),
        "game_window": {
            "start": fmt_time(start),
            "end": fmt_time(end),
            "duration_seconds": int((end - start).total_seconds()),
            "source": "user_cli",
            "package": args.game_package.strip(),
        },
        "time_windows": {
            "T_pre": {"start": fmt_time(start - timedelta(seconds=pre_s)), "end": fmt_time(start)},
            "T_game": {"start": fmt_time(start), "end": fmt_time(end)},
            "T_post": {"start": fmt_time(end), "end": fmt_time(end + timedelta(seconds=post_s))},
        },
        "log_availability": {"kernel_log": bool(logs.get("kernel_log"))},
        "kernel_cpu_summary": {
            "sample_count": kernel_summary.get("sample_count", 0),
            "avg_total_usage": kernel_summary.get("avg_total_usage", 0),
            "max_total_usage": kernel_summary.get("max_total_usage", 0),
            "top_threads": kernel_summary.get("top_threads", []),
        },
        "cpu_core_usage_stats": kernel_summary.get("cpu_core_usage_stats", {}),
        "abnormal_processes": kernel_summary.get("abnormal_processes", []),
        "cpu_samples": cpu_samples,
        "notes": notes,
        "analysis_time": datetime.now().isoformat(timespec="seconds"),
    }

    out_path = Path(args.output) if args.output else log_path / "analysis" / "cpu_probe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已输出: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
