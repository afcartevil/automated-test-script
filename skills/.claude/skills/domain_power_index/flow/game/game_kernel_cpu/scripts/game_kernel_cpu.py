#!/usr/bin/env python3
"""游戏场景 Kernel [K] CPU 与线程 CLI。"""

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
from game_skill_debug import (  # noqa: E402
    add_debug_log_arguments,
    debug_begin,
    debug_end,
)
from game_kernel_cpu_lib import analyze_game_kernel_cpu, references_dir  # noqa: E402
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
    serialize_cpu_samples,
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
        return Path(*parts[:idx]) / "analysis" / "game_kernel_cpu.json"
    return log_path / "analysis" / "game_kernel_cpu.json"


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    pkg = str(data.get("game_package") or gw.get("package") or "").strip()
    return parse_dt(gw.get("start")), parse_dt(gw.get("end")), pkg


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景 Kernel [K] CPU 分析（game_kernel_cpu）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="", help="T_start；可省略若提供 --window-json")
    parser.add_argument("--end", default="", help="T_end；可省略若提供 --window-json")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--game-package", default="", help="游戏包名，覆盖 window-json 中的包名")
    parser.add_argument("--soc-model", default="", help="SoC 型号，匹配 baseline-cpu-cores 平台标准")
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--startup-seconds", type=int, default=60)
    parser.add_argument("--exit-seconds", type=int, default=30)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_kernel_cpu", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    if not log_path.is_dir():
        print(f"日志目录不存在：{log_path}", file=sys.stderr)
        return 2

    start = parse_dt(args.start) if args.start else None
    end = parse_dt(args.end) if args.end else None
    game_package = args.game_package.strip()
    wpath = resolve_window_json_path(log_path, args.window_json or None)
    if wpath.is_file():
            w_start, w_end, w_pkg = _load_window_json(wpath)
            start = start or w_start
            end = end or w_end
            if not game_package:
                game_package = w_pkg
    if not start or not end or end <= start:
        print("无效时间窗：请提供 --start/--end 或有效 --window-json", file=sys.stderr)
        return 2

    result = analyze_game_kernel_cpu(
        log_path,
        start,
        end,
        game_package=game_package,
        soc_model=args.soc_model,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        startup_seconds=max(0, args.startup_seconds),
        exit_seconds=max(0, args.exit_seconds),
        discover_logs=discover_logs,
        parse_kernel=parse_kernel,
        analyze_kernel_samples=analyze_kernel_samples,
        serialize_cpu_samples=serialize_cpu_samples,
        load_baseline_processes=load_baseline_processes,
        load_baseline_cpu_cores=load_baseline_cpu_cores,
        add_event=add_event,
        fmt_time=fmt_time,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        refs_dir=references_dir(),
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_kernel_cpu"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = result.get("kernel_cpu_summary") or {}
    core = result.get("cpu_core_usage_stats") or {}
    print(f"状态: {result.get('status')}")
    print(
        f"[K] 采样: 总计={summary.get('sample_count')} "
        f"T_game={summary.get('T_game_sample_count')} stable={summary.get('stable_sample_count')}"
    )
    print(f"8核 phase={core.get('phase')} abnormal_cores={core.get('abnormal_core_count')}")
    print(f"异常进程: {len(result.get('abnormal_processes') or [])}")
    print(f"已写入: {out_path}")
    debug_end("game_kernel_cpu", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
