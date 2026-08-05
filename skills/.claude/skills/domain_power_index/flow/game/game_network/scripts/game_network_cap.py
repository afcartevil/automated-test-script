#!/usr/bin/env python3
"""游戏场景 networklog/.cap 解析 CLI。

流程：文件名粗筛 → capinfos 确认与 T_game 重叠 → 仅解析重叠文件；
有 T_game 窗时默认 deep：协议/会话/接口统计并判定双通道。

示例：
  python game_network_cap.py <networklog> --window-json <game_time_window.json>
"""

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
    resolve_window_json_path,
)
from game_power_parser import parse_dt  # noqa: E402
from network_cap_parse_lib import analyze_network_caps  # noqa: E402

_CAP_SKILL_SCRIPTS = _SCRIPT_DIR.parent.parent / "game_network_cap" / "scripts"
if str(_CAP_SKILL_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_CAP_SKILL_SCRIPTS))
try:
    from network_cap_power_lib import extract_power_impact  # noqa: E402
except ImportError:  # pragma: no cover
    extract_power_impact = None  # type: ignore[misc, assignment]


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _load_window_json(path: Path) -> tuple[datetime | None, datetime | None]:
    data = json.loads(path.read_text(encoding="utf-8"))
    gw = data.get("game_window") or {}
    return parse_dt(gw.get("start")), parse_dt(gw.get("end"))


def default_output_path(root: Path) -> Path:
    root = root.resolve()
    parts = list(root.parts)
    lower = [p.lower() for p in parts]
    if "converted" in lower:
        idx = lower.index("converted")
        return Path(*parts[:idx]) / "analysis" / "game_network_cap.json"
    if "downloads" in lower:
        idx = lower.index("downloads")
        if idx >= 2:
            return Path(*parts[:idx]) / "analysis" / "game_network_cap.json"
    if root.is_file():
        return root.parent / "analysis" / "game_network_cap.json"
    return root / "analysis" / "game_network_cap.json"


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="解析 networklog/.cap：仅 T_game 重叠文件；默认 deep 做双通道判定"
    )
    parser.add_argument(
        "path",
        help="networklog 目录、含 netlog/NTLog 的设备根、APLog 目录，或单个 .cap",
    )
    parser.add_argument("--start", default="", help="窗口开始（可选）")
    parser.add_argument("--end", default="", help="窗口结束（可选）")
    parser.add_argument("--window-json", default="", help=WINDOW_JSON_HELP)
    parser.add_argument(
        "--deep",
        action="store_true",
        help="对重叠 cap 跑 tshark 协议/会话/接口（有 T_game 窗时默认开启）",
    )
    parser.add_argument(
        "--no-deep",
        action="store_true",
        help="仅做重叠筛选+capinfos，不做 tshark/双通道",
    )
    parser.add_argument("--output", "-o", default="", help="输出 JSON 路径")
    parser.add_argument("--wireshark-dir", default="", help="Wireshark 安装目录")
    parser.add_argument(
        "--auto-install-wireshark",
        action="store_true",
        help="Windows 下缺少 CLI 时尝试 winget 安装",
    )
    args = parser.parse_args(argv)

    root = Path(args.path)
    if not root.exists():
        print(f"路径不存在：{root}", file=sys.stderr)
        return 2

    start = parse_dt(args.start) if args.start else None
    end = parse_dt(args.end) if args.end else None

    wpath: Path | None = None
    if args.window_json:
        wpath = Path(args.window_json)
    else:
        try:
            cand = resolve_window_json_path(root if root.is_dir() else root.parent, None)
            if cand.is_file():
                wpath = cand
        except Exception:  # noqa: BLE001
            wpath = None
        if wpath is None:
            device = root
            if root.name.lower() == "networklog":
                device = root.parent
            elif root.name.lower() == "netlog":
                device = root.parent.parent
            mobile = device / "mobilelog"
            if mobile.is_dir():
                for aplog in sorted(mobile.glob("APLog_*")):
                    j = aplog / "analysis" / "game_time_window.json"
                    if j.is_file():
                        wpath = j
                        break

    if wpath and wpath.is_file():
        w_start, w_end = _load_window_json(wpath)
        start = start or w_start
        end = end or w_end
        print(f"时间窗来源: {wpath}")

    if not (start and end):
        print(
            "警告: 未提供 T_game 时间窗，无法按重叠过滤；将解析全部 cap。"
            " 请传 --window-json 或 --start/--end。",
            file=sys.stderr,
        )

    if args.no_deep:
        do_deep = False
    elif args.deep:
        do_deep = True
    else:
        # 有 T_game 窗时默认 deep（重叠后做双通道）
        do_deep = bool(start and end)
        if do_deep:
            print("已启用 deep（存在 T_game 窗口时默认对重叠 cap 做协议/双通道分析）")

    result = analyze_network_caps(
        root,
        start=start,
        end=end,
        deep=do_deep,
        wireshark_dir=args.wireshark_dir,
        auto_install_wireshark=bool(args.auto_install_wireshark),
    )
    result["analysis_time"] = datetime.now().isoformat(timespec="seconds")
    if wpath and wpath.is_file():
        result["window_json"] = str(wpath)
    if extract_power_impact is not None:
        dur = None
        if start and end and end > start:
            dur = (end - start).total_seconds()
        result["power_impact"] = extract_power_impact(result, window_duration_s=dur)

    out_path = Path(args.output).resolve() if args.output else default_output_path(root)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"状态: {result.get('status')}  "
        f"发现={result.get('cap_count_discovered')}  "
        f"跳过非重叠={result.get('cap_count_skipped')}  "
        f"解析重叠={result.get('cap_count_parsed')}"
    )
    for f in result.get("files") or []:
        print(
            f"  [parse] {Path(f.get('path') or '').name}: "
            f"pkts={f.get('packets')} "
            f"{f.get('start_time')} ~ {f.get('end_time')} "
            f"overlap_s={f.get('overlap_with_window_seconds')}"
            + (f" ERR={f.get('error')}" if f.get("error") else "")
        )
    skipped = result.get("skipped_non_overlap") or []
    if skipped:
        print(f"  跳过 {len(skipped)} 个非重叠 cap（未深解析）")
        for s in skipped[:5]:
            print(f"    - {s.get('name')} ({s.get('skip_reason')})")
        if len(skipped) > 5:
            print(f"    ... 另有 {len(skipped) - 5} 个")

    dual = result.get("dual_channel") or {}
    if dual:
        print(f"双通道: {dual.get('verdict')} — {dual.get('summary')}")
        for ev in (dual.get("evidence") or [])[:4]:
            print(f"  · {ev}")

    print(f"已写入: {out_path}")
    return 0 if result.get("status") in {"ok", "partial", "missing", "no_overlap"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
