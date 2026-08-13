#!/usr/bin/env python3
"""游戏场景后台应用唤醒与服务 CLI（game_background）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"
_GTW_SCRIPTS = _SCRIPT_DIR.parent.parent / "game_time_window" / "scripts"

for p in (_GTW_SCRIPTS, _GAME_SCRIPTS, _SCRIPT_DIR):
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
from game_background_lib import analyze_game_background  # noqa: E402
from game_power_parser import (  # noqa: E402
    add_event,
    discover_logs,
    extract_ts,
    fmt_time,
    iter_lines,
    load_baseline_processes,
    parse_dt,
    phase_for,
    window_for,
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
        return Path(*parts[:idx]) / "analysis" / "game_background.json"
    return log_path / "analysis" / "game_background.json"


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    pkg = str(data.get("game_package") or gw.get("package") or "").strip()
    return parse_dt(gw.get("start")), parse_dt(gw.get("end")), pkg


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="游戏场景后台应用唤醒与服务分析（game_background）"
    )
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--game-package", default="")
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--startup-seconds", type=int, default=60)
    parser.add_argument("--exit-seconds", type=int, default=30)
    parser.add_argument(
        "--no-link-cpu",
        action="store_true",
        help="不读取 game_kernel_cpu.json 做交叉关联",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_background", inputs={k: getattr(args, k) for k in vars(args)})

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

    result = analyze_game_background(
        log_path,
        start,
        end,
        game_package=game_package,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        startup_seconds=args.startup_seconds,
        exit_seconds=args.exit_seconds,
        link_kernel_cpu=not args.no_link_cpu,
        discover_logs=discover_logs,
        extract_ts=extract_ts,
        window_for=window_for,
        iter_lines=iter_lines,
        fmt_time=fmt_time,
        add_event=add_event,
        phase_for=phase_for,
        load_baseline_processes=load_baseline_processes,
        scripts_dir=_GAME_SCRIPTS,
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_background"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    top = result.get("top_background_packages") or []
    during = (result.get("background_summary") or {}).get("during_game") or {}
    inv = result.get("background_investigation") or {}
    s1 = inv.get("step1_process_autostart") or {}
    s2 = inv.get("step2_memory_pss") or {}
    s3 = inv.get("step3_background_download") or {}
    s4 = inv.get("step4_gc_storm") or {}
    print(
        f"步骤1 自启动: starts={s1.get('total_starts')} dies={s1.get('total_dies')} "
        f"restarts={s1.get('total_service_restarts')} "
        f"frequent={s1.get('frequent_autostart')}"
    )
    print(
        f"步骤2 内存PSS: packages={s2.get('package_count')} "
        f"coverage={s2.get('coverage')}"
    )
    print(
        f"步骤3 后台下载: t_game_download={s3.get('t_game_download_count')} "
        f"gcloud={s3.get('gcloud_tencent_download_during_game')}"
    )
    print(
        f"步骤4 GC风暴: count={s4.get('gc_count')} "
        f"{s4.get('gc_per_minute')}/min storm={s4.get('gc_storm')}"
    )
    print(f"状态: {result.get('status')}")
    print(
        f"游戏内: game_related={during.get('game_related_packages')} "
        f"wakelock_pkgs={during.get('wakelock_packages')} "
        f"service_pkgs={during.get('service_active_packages')}"
    )
    if top:
        print(
            f"Top: {top[0].get('package_or_process')} "
            f"boost={top[0].get('boost_ratio')} relation={top[0].get('relation')}"
        )
    print(f"已写入: {out_path}")
    debug_end("game_background", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
