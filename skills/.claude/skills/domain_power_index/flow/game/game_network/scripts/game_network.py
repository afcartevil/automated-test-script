#!/usr/bin/env python3
"""游戏场景网络/RF 分析 CLI（flow 步骤 10）。"""

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
from game_network_lib import analyze_game_network  # noqa: E402
from game_power_parser import discover_logs, extract_ts, fmt_time, iter_lines, parse_dt  # noqa: E402
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
        return Path(*parts[:idx]) / "analysis" / "game_network.json"
    return log_path / "analysis" / "game_network.json"


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    return parse_dt(gw.get("start")), parse_dt(gw.get("end")), ""


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(description="游戏场景网络/RF 分析（game_network）")
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument("--pre-minutes", type=int, default=5)
    parser.add_argument("--post-minutes", type=int, default=3)
    parser.add_argument("--output", default="")
    args = parser.parse_args(argv)
    debug_begin(args, "game_network", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    if not log_path.is_dir():
        print(f"日志目录不存在：{log_path}", file=sys.stderr)
        return 2

    start = parse_dt(args.start) if args.start else None
    end = parse_dt(args.end) if args.end else None
    wpath = resolve_window_json_path(log_path, args.window_json or None)
    if wpath.is_file():
            w_start, w_end, _ = _load_window_json(wpath)
            start = start or w_start
            end = end or w_end
    if not start or not end or end <= start:
        print("无效时间窗：请提供 --start/--end 或有效 --window-json", file=sys.stderr)
        return 2

    result = analyze_game_network(
        log_path,
        start,
        end,
        pre_minutes=args.pre_minutes,
        post_minutes=args.post_minutes,
        discover_logs=discover_logs,
        extract_ts=extract_ts,
        iter_lines=iter_lines,
        window_for=window_for,
        fmt_time=fmt_time,
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    result["skill"] = "game_network"

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    rf = result.get("rf_stats") or {}
    inv = result.get("network_investigation") or {}
    s1 = inv.get("step1_wifi_rssi") or {}
    s2 = inv.get("step2_wifi_scenario") or {}
    s3 = inv.get("step3_cellular_signal") or {}
    s4 = inv.get("step4_ccmni_transfer") or {}
    print(
        f"步骤1 WiFi RSSI: samples={s1.get('sample_count')} "
        f"curve={s1.get('curve_sample_count')} "
        f"avg={s1.get('rssi_dbm_avg')} dBm scope={s1.get('stats_scope')}"
        + (
            f" SSID={(s1.get('wifi_assistant') or {}).get('ssid')}"
            f" netId={(s1.get('wifi_assistant') or {}).get('network_id')}"
            if isinstance(s1.get("wifi_assistant"), dict)
            and (s1.get("wifi_assistant") or {}).get("coverage") == "ok"
            else ""
        )
    )
    dual = inv.get("dual_channel") or {}
    print(
        f"步骤2 场景切换: wifi_changes={s2.get('wifi_interface_changes')} "
        f"mobile_active={s2.get('cellular_data_during_game')} "
        f"dual={dual.get('verdict')}"
    )
    print(
        f"步骤3 蜂窝信号: samples={s3.get('sample_count')} "
        f"rsrp_avg={s3.get('rsrp_avg')} band_changed={s3.get('band_changed')}"
    )
    print(
        f"步骤4 数传: iface={s4.get('primary_interface')} "
        f"rx_delta={s4.get('primary_rx_bytes_delta')} "
        f"align={s4.get('time_alignment')}"
    )
    print(f"状态: {result.get('status')} RF level={rf.get('level')}")
    print(f"已写入: {out_path}")
    debug_end("game_network", result, output_path=out_path, ok=result.get("status") not in {"failed", "error"} if isinstance(result, dict) else True)

    return 0 if result.get("status") != "failed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
