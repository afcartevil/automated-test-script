#!/usr/bin/env python3
"""游戏功耗诊断统一报告 CLI（步骤 12 之后：功耗差确认 + 初步诊断 + AI 建议）。"""

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

from game_diagnosis_report_lib import (  # noqa: E402
    analyze_diagnosis_report,
    write_diagnosis_outputs,
)
from game_log_paths import add_log_path_argument, resolve_log_path  # noqa: E402
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


def _load_json(path: str) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏功耗诊断统一报告（game_diagnosis_report）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--analysis-dir", default="", help="分析产物目录，默认 <log_path>/analysis")
    parser.add_argument(
        "--compare-analysis-dir",
        default="",
        help="对比机 analysis 目录；有则澄清报告双日志对比，无则单机输出",
    )
    parser.add_argument(
        "--log-compare",
        default="",
        help="对比机 APLog 目录（等价于 --compare-analysis-dir <log>/analysis）",
    )
    parser.add_argument(
        "--test-device-label",
        default="",
        help="测试机显示名（双机对比）",
    )
    parser.add_argument(
        "--compare-device-label",
        default="",
        help="对比机显示名（双机对比）",
    )
    parser.add_argument("--meta-json", default="", help="JIRA/功耗对比/已知差/电流图结论 JSON")
    parser.add_argument("--ai-json", default="", help="可选：外部 LLM/Agent 产出的 AI 判断 JSON")
    parser.add_argument("--jira-key", default="")
    parser.add_argument("--device-model", default="")
    parser.add_argument("--issue-url", default="")
    parser.add_argument("--game-title", default="")
    parser.add_argument("--competitor-power-ma", type=float, default=None)
    parser.add_argument("--test-power-ma", type=float, default=None)
    parser.add_argument("--delta-power-ma", type=float, default=None)
    parser.add_argument("--adjusted-delta-ma", type=float, default=None)
    parser.add_argument("--screen-delta-ma", type=float, default=None)
    parser.add_argument("--speaker-delta-ma", type=float, default=None)
    parser.add_argument("--cpu-delta-ma", type=float, default=None)
    parser.add_argument("--rf-delta-ma", type=float, default=None)
    parser.add_argument("--has-abnormal-spike", choices=["true", "false", ""], default="")
    parser.add_argument("--spike-impact", default="", help="异常电流段对平均电流的影响说明")
    parser.add_argument("--avg-delta-without-spike-ma", type=float, default=None)
    parser.add_argument("--waveform-conclusion", default="")
    parser.add_argument("--expected-network", choices=["wifi", "data"], default="wifi")
    parser.add_argument("--output-html", default="", help="默认 analysis/game_power_clarify_report.html")
    args = parser.parse_args(argv)
    debug_begin(args, "game_diagnosis_report", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    analysis_dir = Path(args.analysis_dir) if args.analysis_dir else log_path / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    report_meta = _load_json(args.meta_json)
    for key, val in (
        ("jira_key", args.jira_key),
        ("device_model", args.device_model),
        ("issue_url", args.issue_url),
        ("game_title", args.game_title),
        ("expected_network", args.expected_network),
        ("spike_impact_on_avg", args.spike_impact),
        ("waveform_conclusion", args.waveform_conclusion),
        ("test_device_label", args.test_device_label),
        ("compare_device_label", args.compare_device_label),
    ):
        if val:
            report_meta[key] = val
    for key, val in (
        ("competitor_power_ma", args.competitor_power_ma),
        ("test_power_ma", args.test_power_ma),
        ("delta_power_ma", args.delta_power_ma),
        ("adjusted_delta_ma", args.adjusted_delta_ma),
        ("screen_delta_ma", args.screen_delta_ma),
        ("speaker_delta_ma", args.speaker_delta_ma),
        ("cpu_delta_ma", args.cpu_delta_ma),
        ("rf_delta_ma", args.rf_delta_ma),
        ("avg_delta_without_spike_ma", args.avg_delta_without_spike_ma),
    ):
        if val is not None:
            report_meta[key] = val
    if args.has_abnormal_spike == "true":
        report_meta["has_abnormal_current_spike"] = True
    elif args.has_abnormal_spike == "false":
        report_meta["has_abnormal_current_spike"] = False

    compare_analysis_dir: Path | None = None
    if args.compare_analysis_dir.strip():
        compare_analysis_dir = Path(args.compare_analysis_dir).resolve()
    elif args.log_compare.strip():
        compare_analysis_dir = resolve_log_path(args.log_compare) / "analysis"

    external_ai = _load_json(args.ai_json)
    result = analyze_diagnosis_report(
        analysis_dir,
        report_meta,
        external_ai=external_ai or None,
        compare_analysis_dir=compare_analysis_dir,
    )
    html_name = Path(args.output_html).name if args.output_html else "game_power_clarify_report.html"
    paths = write_diagnosis_outputs(analysis_dir, result, html_name=html_name)
    if args.output_html:
        out = Path(args.output_html)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(result["html"], encoding="utf-8")
        paths["html"] = out

    pd = result["power_delta"]
    diag = result["diagnosis"]
    ai = result["ai_insights"]
    print(f"状态: {result.get('status')}")
    print(
        f"功耗差: I1={pd.get('delta_power_ma_i1')} "
        f"known={pd.get('known_delta_sum_ma')} "
        f"route={(pd.get('routing') or {}).get('decision')}"
    )
    print(f"初步诊断命中: {diag.get('triggered_count')}/{diag.get('total_rules')}")
    for item in (diag.get("primary_causes") or [])[:5]:
        print(f"  [{item.get('priority')}] {item.get('category_title')} — {item.get('label')}")
    print(f"AI: {ai.get('summary')}")
    print(f"已写入: {paths['power_delta']}")
    print(f"已写入: {paths['diagnosis']}")
    print(f"已写入: {paths['ai']}")
    print(f"已写入: {paths['bundle']}")
    print(f"已写入: {paths['root_cause']}")
    print(f"已写入澄清报告: {paths['html']}")
    debug_end("game_diagnosis_report", {"power_delta": pd, "diagnosis": diag, "ai": ai, "paths": {k: str(v) for k, v in paths.items()}}, output_path=paths['html'], ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
