#!/usr/bin/env python3
"""游戏场景温控 CLI（温升 / 降背光 / 限频）。"""

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
from game_thermal_lib import analyze_game_thermal  # noqa: E402
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
        return Path(*parts[:idx]) / "analysis" / "game_thermal.json"
    return log_path / "analysis" / "game_thermal.json"


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    pkg = str(data.get("game_package") or gw.get("package") or "").strip()
    return parse_dt(gw.get("start")), parse_dt(gw.get("end")), pkg


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景温控分析（game_thermal）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--game-package", default="")
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--rise-delta-c", type=float, default=3.0, help="判定温升的最小 delta°C")
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_thermal", inputs={k: getattr(args, k) for k in vars(args)})

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

    result = analyze_game_thermal(
        log_path,
        start,
        end,
        game_package=game_package,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        rise_delta_c_threshold=args.rise_delta_c,
        discover_logs=discover_logs,
        extract_ts=extract_ts,
        window_for=window_for,
        iter_lines=iter_lines,
        fmt_time=fmt_time,
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_thermal"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = result.get("thermal_summary") or {}
    during = summary.get("during_game") or {}
    inv = result.get("thermal_investigation") or {}
    s1 = inv.get("step1_thermal_info") or {}
    s2 = inv.get("step2_cpu_intervention") or {}
    eng = s1.get("engine_temp_stats") or {}
    print(
        f"步骤1 thermal: engine={s1.get('engine_sample_count')} "
        f"scene_game={s1.get('scene_game_count')} "
        f"temp={eng.get('min')}~{eng.get('max')}°C"
    )
    print(
        f"步骤2 CPU介入: detected={s2.get('cpu_intervention_detected')} "
        f"events={s2.get('cpu_intervention_event_count')} "
        f"values={s2.get('intervention_values')}"
    )
    temp = result.get("temperature") or {}
    tgame = temp.get("T_game") or {}
    bl = result.get("thermal_backlight") or {}
    thr = result.get("thermal_throttle") or {}
    print(f"状态: {result.get('status')}")
    report = result.get("thermal_report") or {}
    dim = report.get("backlight_dim") or {}
    freq = report.get("freq_throttle") or {}
    if dim.get("report_summary") or freq.get("report_summary"):
        print(dim.get("report_summary") or f"降背光={during.get('thermal_backlight')}")
        print(freq.get("report_summary") or f"限频={during.get('freq_throttle')}")
    else:
        print(
            f"游戏内: 温升={during.get('temp_rise')} "
            f"降背光={during.get('thermal_backlight')} 限频={during.get('freq_throttle')}"
        )
    print(f"温度 T_game: max={tgame.get('max_c')}°C delta={tgame.get('delta_c')}°C "
          f"curve={len(report.get('temp_timeline') or [])}")
    print(f"降背光事件: {bl.get('upgrade_event_count')} max_level={bl.get('max_level')}")
    print(f"限频: status_max={thr.get('throttle_status_max')} events={thr.get('event_count')}")
    print(f"已写入: {out_path}")
    debug_end("game_thermal", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
