#!/usr/bin/env python3
"""游戏场景 trace / perf-statistic.html 分析 CLI（flow 步骤 8 子能力）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME_SCRIPTS = _SCRIPT_DIR.parent.parent / "scripts"

for p in (_SCRIPT_DIR, _GAME_SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_log_paths import (  # noqa: E402
    WINDOW_JSON_HELP,
    add_log_path_argument,
    resolve_log_path,
    resolve_window_json_path,
)
from game_trace_lib import analyze_game_trace  # noqa: E402
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


def default_output_path(log_path: Path | None) -> Path:
    if log_path is None:
        return Path.cwd() / "analysis" / "game_trace.json"
    parts = list(log_path.resolve().parts)
    lower = [p.lower() for p in parts]
    if "converted" in lower:
        idx = lower.index("converted")
        return Path(*parts[:idx]) / "analysis" / "game_trace.json"
    return log_path / "analysis" / "game_trace.json"


def _load_window_meta(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    return {
        "window_source": str(path),
        "t_game_start": gw.get("start"),
        "t_game_end": gw.get("end"),
        "game_package": data.get("game_package") or gw.get("package"),
        "coverage": "short_trace_sample",
        "note": "HTML 来自短时 trace（通常数秒），不必与 T_game 对齐；仅作采样窗内频率/负载分布证据",
    }


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="解析 MTK perf-statistic.html（或旁路查找），输出 game_trace.json"
    )
    add_log_path_argument(parser, required=False)
    add_debug_log_arguments(parser)
    parser.add_argument(
        "--perf-html",
        default="",
        help="MTK 工具导出的 perf-statistic.html 路径（推荐）",
    )
    parser.add_argument(
        "--trace-path",
        default="",
        help="原始 trace；若同目录存在 perf-statistic.html 会自动解析",
    )
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument(
        "--soc-model",
        default="",
        help="机型/项目代码（如 CN6 / LK7K），查能效表估算 CPU 动态功耗",
    )
    parser.add_argument(
        "--xlsx",
        default="",
        help="能效表 xlsx；默认 game_trace/references/energy_efficiency.xlsx",
    )
    parser.add_argument(
        "--vdd",
        type=float,
        default=4.0,
        help="电池侧等效电压，I_mA=P_mW/VDD（默认 4.0）",
    )
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_trace", inputs={k: getattr(args, k) for k in vars(args)})

    log_path: Path | None = None
    if args.log_path:
        log_path = resolve_log_path(args.log_path)
        if not log_path.is_dir():
            print(f"日志目录不存在：{log_path}", file=sys.stderr)
            return 2

    perf_html = Path(args.perf_html).resolve() if args.perf_html else None
    trace_path = Path(args.trace_path).resolve() if args.trace_path else None
    if perf_html is None and trace_path is None and log_path is not None:
        # Convenience: look under log_path for exported HTML.
        cand = log_path / "perf-statistic.html"
        if cand.is_file():
            perf_html = cand
        else:
            for hit in log_path.rglob("perf-statistic.html"):
                perf_html = hit
                break

    window_meta = None
    if log_path is not None:
        wpath = resolve_window_json_path(log_path, args.window_json or None)
        if wpath.is_file():
            window_meta = _load_window_meta(wpath)
    elif args.window_json:
        wpath = Path(args.window_json).resolve()
        if wpath.is_file():
            window_meta = _load_window_meta(wpath)

    result = analyze_game_trace(
        perf_html=perf_html,
        trace_path=trace_path,
        soc_model=args.soc_model.strip(),
        window_meta=window_meta,
        energy_xlsx=Path(args.xlsx).resolve() if args.xlsx else None,
        vdd_v=float(args.vdd),
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"status={result.get('status')} coverage={result.get('coverage')}")
    findings = result.get("findings") or {}
    if findings.get("summary"):
        print(findings["summary"])
    power = result.get("cpu_power") or {}
    if power.get("status") == "ok":
        print(
            f"cpu_power: {power.get('est_cpu_power_mW')} mW / "
            f"{power.get('est_cpu_current_mA')} mA @ {power.get('vdd_v')}V "
            f"(platform={power.get('platform')})"
        )
    elif power.get("status") and power.get("status") != "skipped":
        print(f"cpu_power: {power.get('status')} {power.get('error') or power.get('reason') or ''}")
    debug_end("game_trace", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"})
    return 0 if result.get("status") in {"ok", "missing"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
