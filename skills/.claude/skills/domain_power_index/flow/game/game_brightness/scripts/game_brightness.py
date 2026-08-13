#!/usr/bin/env python3
"""游戏场景亮度与显示参数 CLI（LCM/HWC/刷新率/ColorMode/thermal）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

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
from display_brightness import parse_hwcomposer_brightness, parse_kernel_backlight  # noqa: E402
from game_brightness_lib import analyze_game_brightness  # noqa: E402
from game_power_parser import add_event  # noqa: E402
from game_time_window_lib import (  # noqa: E402
    discover_logs,
    extract_ts,
    fmt_time,
    iter_lines,
    parse_dt,
    window_for,
)

_PRECOND_SCRIPTS = _SCRIPT_DIR.parent.parent / "game_precondition" / "scripts"
if str(_PRECOND_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_PRECOND_SCRIPTS))
from game_project_resolve import resolve_project_context  # noqa: E402


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
        return Path(*parts[:idx]) / "analysis" / "game_brightness.json"
    return log_path / "analysis" / "game_brightness.json"


def _load_window_from_json(path: Path) -> tuple[datetime | None, datetime | None, str | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    pkg = data.get("game_package") or gw.get("package")
    return parse_dt(gw.get("start")), parse_dt(gw.get("end")), (str(pkg).strip() if pkg else None)


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景亮度与显示参数分析（game_brightness）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="", help="T_start；可省略若提供 --window-json")
    parser.add_argument("--end", default="", help="T_end；可省略若提供 --window-json")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--entry-seconds", type=int, default=60, help="进游戏后观察窗秒数（刷新率/AAL 等）")
    parser.add_argument("--launch-seconds", type=int, default=0, help="启动变光窗秒数，0=使用 analysis-standards 默认")
    parser.add_argument("--game-package", default="", help="游戏包名（背光2.0名单匹配；可省略若 --window-json 含 game_package）")
    parser.add_argument(
        "--project",
        default="",
        help="项目名（匹配 brightness-volume-by-project.yaml，如 项目1）；可从 analysis/game_analysis_meta.json 继承",
    )
    parser.add_argument(
        "--test-case",
        default="",
        help="测试用例：basic/基础场景（等级）或 nps/NPS/最大亮度；可从 meta 继承，默认 basic",
    )
    parser.add_argument(
        "--jira-key",
        default="",
        help="可选：从 JIRA 解析项目/场景（通常由 flow 前置步骤写入 meta）",
    )
    parser.add_argument(
        "--max-brightness-scenario",
        action="store_true",
        help="JIRA 标注为最大亮度场景时指定（仅影响背光2.0步骤）；未指定则按测试前亮度等级自动推断",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_brightness", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    if not log_path.is_dir():
        print(f"日志目录不存在：{log_path}", file=sys.stderr)
        return 2

    proj_ctx = resolve_project_context(
        log_path=log_path,
        project=args.project.strip() or None,
        test_case=args.test_case.strip() or None,
        jira_key=args.jira_key.strip() or None,
        interactive=False,
        persist=True,
    )
    project = str(proj_ctx.get("project") or proj_ctx.get("project_requested") or "").strip() or None
    test_case = str(proj_ctx.get("test_case") or "basic").strip() or None

    start = parse_dt(args.start) if args.start else None
    end = parse_dt(args.end) if args.end else None
    game_package = args.game_package.strip() or None
    wpath = resolve_window_json_path(log_path, args.window_json or None)
    if wpath.is_file():
        w_start, w_end, w_pkg = _load_window_from_json(wpath)
        start = start or w_start
        end = end or w_end
        game_package = game_package or w_pkg
    if not start or not end or end <= start:
        print("无效时间窗：请提供 --start/--end 或有效 --window-json", file=sys.stderr)
        return 2

    result = analyze_game_brightness(
        log_path,
        start,
        end,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        entry_seconds=max(0, args.entry_seconds),
        launch_window_seconds=max(0, args.launch_seconds) or None,
        game_package=game_package,
        max_brightness_scenario=True if args.max_brightness_scenario else None,
        project=project,
        test_case=test_case,
        discover_logs=discover_logs,
        parse_kernel_backlight=parse_kernel_backlight,
        parse_hwcomposer_brightness=parse_hwcomposer_brightness,
        add_event=add_event,
        extract_ts=extract_ts,
        window_for=window_for,
        iter_lines=iter_lines,
        fmt_time=fmt_time,
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_brightness"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    pre = result.get("pre_test_brightness") or {}
    ba = result.get("brightness_analysis") or {}
    rr = (result.get("refresh_rate") or {}).get("T_game") or {}
    inv = result.get("brightness_investigation") or {}
    s1 = inv.get("step1_test_setting") or {}
    s2 = inv.get("step2_auto_backlight") or {}
    s3 = inv.get("step3_backlight_2_0") or {}
    s4 = inv.get("step4_aal_strategy") or {}
    s5 = inv.get("step5_thermal_control") or {}
    s6 = inv.get("step6_refresh_rate") or {}
    if s1.get("compare_mode") == "nits" or s1.get("measured_nits") is not None or s1.get("brightness_level") is not None:
        align = s1.get("aligned_with_standard")
        align_s = "对齐" if align is True else ("未对齐" if align is False else "未知")
        if s1.get("compare_mode") == "nits":
            metric = s1.get("align_metric") or "level"
            if metric == "level" or s1.get("brightness_level") is not None:
                measured_s = f"level={s1.get('brightness_level')}"
            elif metric == "curve" or s1.get("hwc_curve_val") is not None:
                measured_s = f"curve={s1.get('hwc_curve_val')}"
            else:
                measured_s = f"nits={s1.get('measured_nits')}"
            print(
                f"步骤1 测试亮度(NPS): {measured_s} "
                f"expected_level={s1.get('expected_level')} metric={metric} "
                f"({s1.get('project')}/{s1.get('test_case_label')}, {align_s})"
            )
        else:
            print(
                f"步骤1 测试设置亮度: measured={s1.get('brightness_level')} "
                f"expected={s1.get('expected_level')} "
                f"({s1.get('project')}/{s1.get('test_case_label')}, {align_s})"
            )
    if s2.get("enabled") is not None:
        print(f"步骤2 自动背光: {'开启' if s2['enabled'] else '关闭'}")
    if not s3.get("skipped"):
        print(f"步骤3 背光2.0: {s3.get('message') or ('生效' if s3.get('effective') else '待核对')}")
    if s4.get("report_summary"):
        print(f"步骤4 AAL: {s4.get('report_summary')}")
    elif s4.get("effective") is False:
        print("步骤4 AAL: 未生效（main log 无 AALService）")
    elif s4.get("sample_count"):
        print(f"步骤4 AAL: BL {s4.get('first_bl')}→{s4.get('last_bl')}")
    if s5.get("triggered"):
        print(f"步骤5 温控降亮: 触发 {s5.get('hit_count')} 次（测试手法风险）")
    sup = (s6.get("supported_fps") or {}).get("last_hz")
    act = (s6.get("actual_fps") or {}).get("last_hz")
    if sup is not None or act is not None:
        print(f"步骤6 刷新率: PowerHal={sup}Hz · hwcomposer={act}Hz")
    print(f"状态: {result.get('status')}")
    pg = pre.get("pre_game_setting") or {}
    if pg.get("coverage") == "ok":
        parts = []
        by_src = pg.get("by_source") or {}
        bc = by_src.get("brightness_collector") or {}
        if bc.get("brightness_level") is not None:
            parts.append(f"等级={bc['brightness_level']}/255")
        elif pg.get("brightness_level") is not None:
            parts.append(f"等级={pg['brightness_level']}/255")
        if pg.get("curve_val") is not None:
            parts.append(f"曲线={pg['curve_val']}/4095")
        print(f"测试前亮度(末值): {' | '.join(parts) or pg.get('pattern_id')}")
    else:
        lcm_b = (pre.get("lcm") or {}).get("level")
        hwc_b = (pre.get("hwc") or {}).get("brightness_val")
        print(f"测试前亮度: LCM level={lcm_b} | HWC val={hwc_b}")
    launch = ba.get("launch_window") or {}
    in_game = ba.get("in_game_changes") or {}
    print(
        f"启动变光({launch.get('window_seconds')}s): "
        f"phases={launch.get('phase_count')} "
        f"curve={launch.get('stats', {}).get('curve_min')}~{launch.get('stats', {}).get('curve_max')}"
    )
    print(
        f"游戏内变光: phases={in_game.get('phase_count')} "
        f"curve={in_game.get('stats', {}).get('curve_min')}~{in_game.get('stats', {}).get('curve_max')}"
    )
    entry_n = len((result.get("game_entry_brightness") or {}).get("events") or [])
    print(f"进游戏变光事件(LCM/HWC): {entry_n}")
    print(
        f"T_game 刷新率: stable={rr.get('stable_hz')}Hz "
        f"range={rr.get('min_hz')}~{rr.get('max_hz')}Hz samples={rr.get('sample_count')}"
    )
    print(f"已写入: {out_path}")
    debug_end("game_brightness", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
