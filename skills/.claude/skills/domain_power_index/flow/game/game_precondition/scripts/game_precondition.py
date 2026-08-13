#!/usr/bin/env python3
"""游戏测试前置条件检查 CLI（flow 步骤 4）。"""

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
from game_precondition_lib import analyze_game_precondition  # noqa: E402
from game_power_parser import discover_logs, extract_ts, fmt_time, iter_lines, parse_dt  # noqa: E402
from game_project_resolve import resolve_project_context  # noqa: E402
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
        return Path(*parts[:idx]) / "analysis" / "game_precondition.json"
    return log_path / "analysis" / "game_precondition.json"


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    pkg = str(data.get("game_package") or gw.get("package") or "").strip()
    return parse_dt(gw.get("start")), parse_dt(gw.get("end")), pkg


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏测试前置条件检查（game_precondition）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--game-package", default="")
    parser.add_argument(
        "--project",
        default="",
        help="项目名（匹配 brightness-volume-by-project.yaml，如 项目1）；路径模式未指定时会交互选择",
    )
    parser.add_argument(
        "--test-case",
        default="",
        help="测试用例：basic/基础场景 或 nps/NPS；可从 JIRA/meta 推断，默认 basic",
    )
    parser.add_argument(
        "--jira-key",
        default="",
        help="JIRA 单号：从摘要/描述/affect_project 解析项目与测试场景",
    )
    parser.add_argument(
        "--no-interactive",
        action="store_true",
        help="禁止交互选项目（CI/非 TTY）；缺项目时仅写 meta 提示",
    )
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_precondition", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    if not log_path.is_dir():
        print(f"日志目录不存在：{log_path}", file=sys.stderr)
        return 2

    ctx = resolve_project_context(
        log_path=log_path,
        project=args.project.strip() or None,
        test_case=args.test_case.strip() or None,
        jira_key=args.jira_key.strip() or None,
        interactive=False if args.no_interactive else None,
        persist=True,
    )
    project = str(ctx.get("project") or ctx.get("project_requested") or "").strip()
    test_case = str(ctx.get("test_case") or "basic").strip()
    if not project:
        print(
            "未解析到项目。请传 --project，或 --jira-key，或在 TTY 下选择飞书亮度和音量表项目。",
            file=sys.stderr,
        )
    else:
        print(
            f"项目上下文: project={project} test_case={test_case} "
            f"source={ctx.get('source')} volume_index={ctx.get('volume_index')} "
            f"brightness_level={ctx.get('brightness_level')}"
        )

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

    result = analyze_game_precondition(
        log_path,
        start,
        end,
        game_package=game_package,
        project=project,
        test_case=test_case,
        pre_minutes=args.pre_minutes,
        discover_logs=discover_logs,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        fmt_time=fmt_time,
    )
    result["project_context"] = {
        "project": project,
        "test_case": test_case,
        "source": ctx.get("source"),
        "jira_key": ctx.get("jira_key"),
        "table_url": ctx.get("table_url"),
    }
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_precondition"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    tc = result.get("test_conditions") or {}
    sc = tc.get("scenario") or {}
    tags = tc.get("tags") or []
    br = next((t for t in tags if t.get("id") == "brightness"), None)
    vol = next((t for t in tags if t.get("id") == "volume"), None)
    if br:
        if br.get("compare_mode") == "nits":
            metric = br.get("align_metric") or "level"
            if br.get("numeric_level") is not None:
                measured_s = f"level={br.get('numeric_level')}"
            elif br.get("numeric_curve") is not None:
                measured_s = f"curve={br.get('numeric_curve')}"
            elif br.get("numeric_nits") is not None:
                measured_s = f"{br.get('numeric_nits')}nit"
            else:
                measured_s = br.get("value") or "未检测到"
            exp_lv = br.get("expected_level")
            exp_s = f"level={exp_lv}" if exp_lv is not None else "最大亮度(level)"
            print(
                f"测试亮度(NPS): measured={measured_s} "
                f"expected={exp_s} metric={metric} status={br.get('status')} "
                f"({sc.get('project')}/{sc.get('label')})"
            )
        else:
            print(
                f"测试亮度: measured={br.get('numeric_level')} expected={br.get('expected_level')} "
                f"status={br.get('status')} ({sc.get('project')}/{sc.get('label')})"
            )
    if vol:
        print(
            f"测试音量: measured={vol.get('numeric_volume_index')} "
            f"expected={vol.get('expected_volume_index')} "
            f"status={vol.get('status')} ({sc.get('project')}/{sc.get('label')})"
        )
    print(f"状态: {result.get('status')}")
    print(f"已写入: {out_path}")
    debug_end("game_precondition", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
