#!/usr/bin/env python3
"""游戏功耗澄清原因判断 CLI（flow 步骤 13）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"

for p in (_GAME_SCRIPTS, _SCRIPT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_log_paths import add_log_path_argument, resolve_log_path  # noqa: E402
from game_root_cause_lib import analyze_root_cause  # noqa: E402
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


def _load_meta_json(path: str) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏功耗澄清原因判断（game_root_cause）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--analysis-dir", default="", help="分析产物目录，默认 <log_path>/analysis")
    parser.add_argument("--summary-json", default="", help="步骤 12 汇总 JSON（可选）")
    parser.add_argument("--output-json", default="", help="判断结果 JSON，默认 game_root_cause.json")
    parser.add_argument("--output-html", default="", help="澄清报告 HTML，默认 game_power_clarify_report.html")
    parser.add_argument("--meta-json", default="", help="报告元数据 JSON（JIRA/机型/功耗对比等）")
    parser.add_argument("--jira-key", default="")
    parser.add_argument("--device-model", default="")
    parser.add_argument("--issue-url", default="")
    parser.add_argument("--priority", default="")
    parser.add_argument("--game-title", default="")
    parser.add_argument("--competitor-power-ma", type=float, default=None)
    parser.add_argument("--test-power-ma", type=float, default=None)
    parser.add_argument("--delta-power-ma", type=float, default=None)
    parser.add_argument("--adjusted-delta-ma", type=float, default=None)
    parser.add_argument("--expected-network", choices=["wifi", "data"], default="wifi")
    args = parser.parse_args(argv)
    debug_begin(args, "game_root_cause", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    analysis_dir = Path(args.analysis_dir) if args.analysis_dir else log_path / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    report_meta = _load_meta_json(args.meta_json)
    for key, val, arg in (
        ("jira_key", args.jira_key, args.jira_key),
        ("device_model", args.device_model, args.device_model),
        ("issue_url", args.issue_url, args.issue_url),
        ("priority", args.priority, args.priority),
        ("game_title", args.game_title, args.game_title),
        ("expected_network", args.expected_network, args.expected_network),
    ):
        if arg:
            report_meta[key] = val
    for key, val in (
        ("competitor_power_ma", args.competitor_power_ma),
        ("test_power_ma", args.test_power_ma),
        ("delta_power_ma", args.delta_power_ma),
        ("adjusted_delta_ma", args.adjusted_delta_ma),
    ):
        if val is not None:
            report_meta[key] = val

    if args.summary_json:
        src = Path(args.summary_json).resolve()
        dst = analysis_dir / "game_power_compare_summary.json"
        if src != dst:
            dst.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")

    result = analyze_root_cause(analysis_dir, report_meta)
    judgment = result["judgment"]

    out_json = Path(args.output_json) if args.output_json else analysis_dir / "game_root_cause.json"
    out_html = Path(args.output_html) if args.output_html else analysis_dir / "game_power_clarify_report.html"

    payload = {
        "status": judgment.get("status", "ok"),
        "log_path": str(log_path),
        "analysis_dir": str(analysis_dir),
        "triggered_count": judgment.get("triggered_count", 0),
        "primary_causes": judgment.get("primary_causes", []),
        "categories": judgment.get("categories", {}),
        "findings": judgment.get("findings", []),
        "brightness_findings": result.get("brightness_findings", {}),
        "volume_findings": result.get("volume_findings", {}),
        "report_meta": report_meta,
        "html_output": str(out_html),
    }
    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out_html.write_text(result["html"], encoding="utf-8")

    print(f"状态: {payload['status']}")
    print(f"命中规则: {payload['triggered_count']}/{judgment.get('total_rules', 0)}")
    bf = payload.get("brightness_findings") or {}
    if bf.get("coverage") != "missing":
        pg = bf.get("pre_game_setting") or {}
        launch = bf.get("launch_window") or {}
        in_game = bf.get("in_game_changes") or {}
        print(
            f"亮度: 测试前 等级={pg.get('brightness_level')} 曲线={pg.get('curve_val')} | "
            f"启动变光 {launch.get('phase_count', 0)}段 | 游戏内 {in_game.get('phase_count', 0)}段"
        )
    vf = payload.get("volume_findings") or {}
    if vf.get("coverage") != "missing":
        pre_v = vf.get("pre_test_setting") or {}
        ing_v = vf.get("in_game_volume") or {}
        print(
            f"音量: 测试前 index={pre_v.get('index')} ({pre_v.get('index_pct')}%) | "
            f"游戏内 {'变音量' if ing_v.get('changed') else '恒定'} "
            f"{ing_v.get('index_min')}~{ing_v.get('index_max')}"
        )
    for item in judgment.get("primary_causes", [])[:5]:
        print(f"  [{item.get('priority')}] {item.get('category_title')} — {item.get('label')}")
    print(f"已写入: {out_json}")
    print(f"已写入: {out_html}")
    debug_end("game_root_cause", payload, output_path=out_html, ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
