#!/usr/bin/env python3
"""游戏场景 CPU/GPU/DDR 分析 CLI（flow 步骤 8）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"
_GKC_SCRIPTS = _SCRIPT_DIR.parent.parent / "game_kernel_cpu" / "scripts"
_GTW_SCRIPTS = _SCRIPT_DIR.parent.parent / "game_time_window" / "scripts"

for p in (_GTW_SCRIPTS, _GKC_SCRIPTS, _GAME_SCRIPTS, _SCRIPT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_log_paths import (  # noqa: E402
    WINDOW_JSON_HELP,
    add_log_path_argument,
    resolve_log_path,
    resolve_window_json_path,
)
from game_cpu_gpu_ddr_lib import analyze_game_cpu_gpu_ddr  # noqa: E402
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
    parse_main_sys,
    serialize_cpu_samples,
)
from game_time_window_lib import window_for  # noqa: E402
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
        return Path(*parts[:idx]) / "analysis" / "game_cpu_gpu_ddr.json"
    return log_path / "analysis" / "game_cpu_gpu_ddr.json"


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    pkg = str(data.get("game_package") or gw.get("package") or "").strip()
    return parse_dt(gw.get("start")), parse_dt(gw.get("end")), pkg


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景 CPU/GPU/DDR 分析（game_cpu_gpu_ddr）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--game-package", default="")
    parser.add_argument("--soc-model", default="")
    parser.add_argument(
        "--trace-path",
        default="",
        help="原始 trace；若旁路有 perf-statistic.html 会自动解析（步骤 3）",
    )
    parser.add_argument(
        "--perf-html",
        default="",
        help="MTK 工具导出的 perf-statistic.html（步骤 3，推荐）",
    )
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--startup-seconds", type=int, default=60)
    parser.add_argument("--exit-seconds", type=int, default=30)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_cpu_gpu_ddr", inputs={k: getattr(args, k) for k in vars(args)})

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

    trace_path = Path(args.trace_path).resolve() if args.trace_path else None
    perf_html = Path(args.perf_html).resolve() if args.perf_html else None

    result = analyze_game_cpu_gpu_ddr(
        log_path,
        start,
        end,
        game_package=game_package,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        startup_seconds=args.startup_seconds,
        exit_seconds=args.exit_seconds,
        soc_model=args.soc_model.strip(),
        trace_path=trace_path,
        perf_html=perf_html,
        discover_logs=discover_logs,
        extract_ts=extract_ts,
        window_for=window_for,
        iter_lines=iter_lines,
        fmt_time=fmt_time,
        add_event=add_event,
        parse_kernel=parse_kernel,
        analyze_kernel_samples=analyze_kernel_samples,
        load_baseline_processes=load_baseline_processes,
        load_baseline_cpu_cores=load_baseline_cpu_cores,
        serialize_cpu_samples=serialize_cpu_samples,
        parse_main_sys=parse_main_sys,
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_cpu_gpu_ddr"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    k = result.get("kernel_cpu") or {}
    inv = result.get("cpu_gpu_ddr_investigation") or {}
    s1 = inv.get("step1_touch_boost") or {}
    s2 = inv.get("step2_ddr") or {}
    s3 = inv.get("step3_trace") or {}
    s4 = inv.get("step4_frame_rate") or {}
    s5 = inv.get("step5_thermal_throttle") or {}
    perf = result.get("cpu_perf_lock") or {}
    fps = result.get("frame_rate") or {}
    print(f"状态: {result.get('status')}")
    if s1.get("event_count"):
        dur = s1.get("durations_ms") or []
        print(f"步骤1 滑动提频: {s1['event_count']} 次" + (f" duration={dur[-1]}ms" if dur else ""))
    if s2.get("sample_count"):
        print(f"步骤2 DDR: {s2['sample_count']} 次 opp={len(s2.get('opp_stats') or [])}")
    if s3.get("status") == "ok" and s3.get("summary"):
        print(f"步骤3 trace: {s3['summary']}")
    elif s3.get("coverage") in {"pending", "missing"}:
        print(f"步骤3 trace: {s3.get('coverage')} — {s3.get('note') or '无 perf-statistic.html'}")
    gl = s4.get("game_layer") or {}
    if gl.get("avg_fps") is not None:
        print(
            f"步骤4 游戏帧率: avg={gl.get('avg_fps')} "
            f"min={gl.get('min_fps')} max={gl.get('max_fps')}"
        )
    if s5.get("throttled_in_game"):
        print(f"步骤5 thermal限频: 触发 {len(s5.get('throttled_hits') or [])} 次")
    print(f"异常进程: {len(k.get('abnormal_processes') or [])}")
    if perf.get("coverage") == "ok":
        top = (perf.get("by_strategy_idx") or [])[:3]
        brief = ", ".join(
            f"idx{r.get('idx')}×{r.get('acquire_count')}" for r in top if r.get("idx") is not None
        )
        print(f"perfLockAcq(T_game): {perf.get('total_acquire_count')} 次 — {brief}")
    if fps.get("coverage") == "ok":
        mg = fps.get("main_game_layer") or {}
        if mg:
            print(
                f"游戏图层 fps: avg={mg.get('avg_queuebuffer_fps')} "
                f"min={mg.get('min_queuebuffer_fps')} max={mg.get('max_queuebuffer_fps')} "
                f"({mg.get('sample_count')} 采样)"
            )
        below = fps.get("game_below_avg_fps") or {}
        periods = below.get("periods") or []
        if periods:
            bsum = below.get("summary") or {}
            print(
                f"低于均值帧段: {bsum.get('period_count')} 段, "
                f"合计 {bsum.get('total_duration_seconds')}s, "
                f"段内均值 {bsum.get('weighted_avg_fps')} fps"
            )
        print(f"图层帧率: T_game 共 {fps.get('layer_count')} 个图层")
    print(f"已写入: {out_path}")
    debug_end("game_cpu_gpu_ddr", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
