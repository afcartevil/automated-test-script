#!/usr/bin/env python3
"""游戏电流波形与日志关联 CLI（flow 步骤 13）。"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"

for p in (_GAME_SCRIPTS, _SCRIPT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_current_log_correlate_lib import (  # noqa: E402
    analyze_current_log_correlate,
    write_correlate_outputs,
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


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="电流波形与日志关联（game_current_log_correlate）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--analysis-dir", default="", help="默认 <log_path>/analysis")
    parser.add_argument("--pt5", default="", help="pt5 / csv / json 电流文件路径")
    parser.add_argument("--pt5-dir", default="", help="在目录内搜索电流文件")
    parser.add_argument("--jira-key", default="", help="按 JIRA 单号旁路查找附件")
    parser.add_argument("--threshold-ma", type=float, default=20.0)
    parser.add_argument("--window-sec", type=float, default=10.0)
    parser.add_argument("--step-sec", type=float, default=2.0)
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument(
        "--pt5-offset-sec",
        type=float,
        default=0.0,
        help="pt5 相对 T_game.start 的偏移秒（正=电流晚于日志）",
    )
    parser.add_argument("--output", default="", help="JSON 输出路径，默认 analysis/game_current_log_correlate.json")
    args = parser.parse_args(argv)
    debug_begin(args, "game_current_log_correlate", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    analysis_dir = Path(args.analysis_dir) if args.analysis_dir else log_path / "analysis"

    try:
        result = analyze_current_log_correlate(
            log_path=log_path,
            analysis_dir=analysis_dir,
            pt5_path=args.pt5 or None,
            pt5_dir=args.pt5_dir or None,
            jira_key=args.jira_key,
            threshold_ma=args.threshold_ma,
            window_sec=args.window_sec,
            step_sec=args.step_sec,
            top_n=args.top_n,
            pt5_offset_sec=args.pt5_offset_sec,
        )
    except Exception as exc:  # noqa: BLE001 — CLI 边界：写 skipped/error 便于 flow 继续
        result = {
            "skill": "game_current_log_correlate",
            "status": "error",
            "message": str(exc),
            "log_path": str(log_path),
            "raised_windows": [],
            "waveform_analysis": {
                "has_abnormal_spike": None,
                "conclusion": f"电流关联失败: {exc}",
                "coverage": "error",
                "source": "game_current_log_correlate",
            },
        }

    paths = write_correlate_outputs(analysis_dir, result)
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(paths["json"].read_text(encoding="utf-8"), encoding="utf-8")
        paths["json"] = out

    print(f"状态: {result.get('status')}")
    if result.get("status") == "skipped":
        print(result.get("message") or "skipped")
    else:
        print(result.get("summary") or result.get("message") or "")
        for w in (result.get("raised_windows") or [])[:5]:
            print(
                f"  #{w.get('rank')} {w.get('relative_time')} "
                f"+{w.get('mean_raise_ma')}mA → {w.get('primary_cause_label')}"
            )
    print(f"已写入: {paths['json']}")
    print(f"已写入: {paths['html']}")
    ok = result.get("status") in {"ok", "skipped"}
    debug_end(
        "game_current_log_correlate",
        result,
        output_path=paths["json"],
        ok=ok,
    )
    # skipped / ok 均返回 0，不阻断 flow；error 返回 0 也允许继续（产物已写）
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
