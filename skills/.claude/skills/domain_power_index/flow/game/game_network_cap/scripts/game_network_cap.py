#!/usr/bin/env python3
"""游戏场景 networklog/.cap 功耗影响分析 CLI（flow 条件步骤）。

门禁：日志侧存在 networklog，且有与 T_game 重叠的 .cap → 启动解析；
否则写出 status=skipped，不跑 tshark。

示例：
  python game_network_cap.py <APLog> --window-json <game_time_window.json>
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_GAME = _SCRIPT_DIR.parent.parent
_GAME_SCRIPTS = _GAME / "scripts"
_GTW_SCRIPTS = _GAME / "game_time_window" / "scripts"
_NET_SCRIPTS = _GAME / "game_network" / "scripts"

for p in (_GTW_SCRIPTS, _GAME_SCRIPTS, _NET_SCRIPTS, _SCRIPT_DIR):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from game_log_paths import (  # noqa: E402
    WINDOW_JSON_HELP,
    add_log_path_argument,
    resolve_log_path,
    resolve_window_json_path,
)
from game_power_parser import parse_dt  # noqa: E402
from game_skill_debug import (  # noqa: E402
    add_debug_log_arguments,
    debug_begin,
    debug_end,
)
from network_cap_parse_lib import (  # noqa: E402
    analyze_network_caps,
    probe_networklog_tgame_caps,
)
from network_cap_power_lib import extract_power_impact  # noqa: E402


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def default_output_path(log_path: Path) -> Path:
    parts = list(log_path.resolve().parts)
    lower = [p.lower() for p in parts]
    if "converted" in lower:
        # 双机 converted 时仍写入该 APLog 的 analysis，避免互相覆盖
        return log_path / "analysis" / "game_network_cap.json"
    return log_path / "analysis" / "game_network_cap.json"


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    return parse_dt(gw.get("start")), parse_dt(gw.get("end"))


def _window_duration_s(start: datetime | None, end: datetime | None) -> float | None:
    if start and end and end > start:
        return (end - start).total_seconds()
    return None


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="networklog/.cap → T_game 重叠解析 + 功耗影响因子（有门禁）"
    )
    add_log_path_argument(parser)
    add_debug_log_arguments(parser)
    parser.add_argument("--start", default="", help="窗口开始（可选）")
    parser.add_argument("--end", default="", help="窗口结束（可选）")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument(
        "--force",
        action="store_true",
        help="跳过门禁，强制解析（仍按 T_game 重叠过滤）",
    )
    parser.add_argument(
        "--deep",
        action="store_true",
        help="对重叠 cap 跑 tshark（有 T_game 时默认开启）",
    )
    parser.add_argument(
        "--no-deep",
        action="store_true",
        help="仅重叠筛选+capinfos，不做 tshark/双通道",
    )
    parser.add_argument("--output", "-o", default="", help="输出 JSON 路径")
    parser.add_argument("--wireshark-dir", default="", help="Wireshark 安装目录")
    parser.add_argument(
        "--auto-install-wireshark",
        action="store_true",
        help="Windows 下缺少 CLI 时尝试 winget 安装",
    )
    parser.add_argument(
        "--device-label",
        default="",
        help="可选：额外写入 workspace analysis/game_network_cap_<label>.json",
    )
    args = parser.parse_args(argv)
    debug_begin(args, "game_network_cap", inputs={k: getattr(args, k) for k in vars(args)})

    log_path = resolve_log_path(args.log_path)
    if not log_path.exists():
        print(f"路径不存在：{log_path}", file=sys.stderr)
        debug_end("game_network_cap", outputs={"error": "missing path"}, ok=False)
        return 2

    start = parse_dt(args.start) if args.start else None
    end = parse_dt(args.end) if args.end else None
    wpath = resolve_window_json_path(log_path, args.window_json or None)
    if wpath.is_file():
        w_start, w_end = _load_window_json(wpath)
        start = start or w_start
        end = end or w_end
        print(f"时间窗来源: {wpath}")

    probe = probe_networklog_tgame_caps(log_path, start=start, end=end)
    print(
        f"门禁: should_run={probe.get('should_run')} reason={probe.get('reason')} "
        f"caps={probe.get('cap_count_discovered')} candidates={probe.get('candidate_cap_count')}"
    )

    out_path = Path(args.output).resolve() if args.output else default_output_path(log_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if not probe.get("should_run") and not args.force:
        result = {
            "status": "skipped",
            "skill": "game_network_cap",
            "gate": probe,
            "power_impact": extract_power_impact({"status": "skipped", "errors": [probe.get("reason")]}),
            "analysis_time": datetime.now().isoformat(timespec="seconds"),
            "input_root": str(log_path.resolve()),
            "window_json": str(wpath) if wpath.is_file() else None,
            "notes": [
                "未启动：需同时满足 networklog 存在，且文件名粗筛有与 T_game 重叠的 .cap",
                "可用 --force 强制解析",
            ],
        }
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已跳过，写入: {out_path}")
        debug_end(
            "game_network_cap",
            outputs={"status": "skipped", "reason": probe.get("reason"), "output": str(out_path)},
            output_path=out_path,
            ok=True,
        )
        return 0

    if args.no_deep:
        do_deep = False
    elif args.deep:
        do_deep = True
    else:
        do_deep = bool(start and end)
        if do_deep:
            print("已启用 deep（存在 T_game 窗口时默认对重叠 cap 做协议/双通道分析）")

    result = analyze_network_caps(
        log_path,
        start=start,
        end=end,
        deep=do_deep,
        wireshark_dir=args.wireshark_dir,
        auto_install_wireshark=bool(args.auto_install_wireshark),
    )
    result["gate"] = probe
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    if wpath.is_file():
        result["window_json"] = str(wpath)

    dur = _window_duration_s(start, end)
    result["power_impact"] = extract_power_impact(result, window_duration_s=dur)

    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    label = (args.device_label or "").strip()
    if label:
        # 额外落一份带机型标签的副本，便于 workspace 级双机归档
        parts = list(log_path.resolve().parts)
        lower = [p.lower() for p in parts]
        ws_analysis: Path | None = None
        if "converted" in lower:
            idx = lower.index("converted")
            ws_analysis = Path(*parts[:idx]) / "analysis"
        elif "downloads" in lower:
            idx = lower.index("downloads")
            ws_analysis = Path(*parts[:idx]) / "analysis"
        if ws_analysis is not None:
            ws_analysis.mkdir(parents=True, exist_ok=True)
            labeled = ws_analysis / f"game_network_cap_{label}.json"
            labeled.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            result["labeled_output"] = str(labeled)
            print(f"标签副本: {labeled}")

    print(
        f"状态: {result.get('status')}  "
        f"发现={result.get('cap_count_discovered')}  "
        f"跳过非重叠={result.get('cap_count_skipped')}  "
        f"解析重叠={result.get('cap_count_parsed')}"
    )
    pi = result.get("power_impact") or {}
    print(f"功耗影响: level={pi.get('level')} has_impact={pi.get('has_impact')} — {pi.get('summary')}")
    for f in (pi.get("impact_factors") or [])[:5]:
        print(f"  · {f.get('title')}: {f.get('power_hint')}")

    print(f"已写入: {out_path}")
    debug_end(
        "game_network_cap",
        outputs={
            "status": result.get("status"),
            "power_impact_level": pi.get("level"),
            "has_impact": pi.get("has_impact"),
            "output": str(out_path),
        },
        output_path=out_path,
        ok=result.get("status") in {"ok", "partial", "missing", "no_overlap", "skipped"},
    )
    return 0 if result.get("status") in {"ok", "partial", "missing", "no_overlap", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
