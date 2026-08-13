#!/usr/bin/env python3
"""Bugreport AudioMix 持锁时间轴 — CLI 入口。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _scripts_dir() -> Path:
    return Path(__file__).resolve().parent / "scripts"


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="解析 bugreport txt 中 AudioMix 持锁时间轴"
    )
    parser.add_argument(
        "path",
        help="bugreport 目录或 bugreport-*.txt 文件路径",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="JSON 输出路径（默认与 txt 同目录 bugreport_audiomix.json）",
    )
    parser.add_argument(
        "--output-txt",
        default="",
        help="文本报告路径（默认与 txt 同目录 bugreport_audiomix.txt）",
    )
    parser.add_argument(
        "--output-html",
        default="",
        help="HTML 时间轴路径（默认与 txt 同目录 bugreport_audiomix.html）",
    )
    args = parser.parse_args()

    scripts = _scripts_dir()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from parse_audiomix import (  # noqa: E402
        analyze_bugreport,
        format_html_report,
        format_text_report,
        report_to_json,
    )

    src = Path(args.path.strip())
    if not src.exists():
        print(f"路径不存在: {src}", file=sys.stderr)
        return 1

    report = analyze_bugreport(src)
    txt_path = Path(report.bugreport_txt)
    out_dir = txt_path.parent

    out_json = Path(args.output_json) if args.output_json else out_dir / "bugreport_audiomix.json"
    out_txt = Path(args.output_txt) if args.output_txt else out_dir / "bugreport_audiomix.txt"
    out_html = Path(args.output_html) if args.output_html else out_dir / "bugreport_audiomix.html"

    payload = report_to_json(report)
    payload["meta"] = {
        "tool": "bugreport_audiomix/run_bugreport_audiomix.py",
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }

    out_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out_txt.write_text(format_text_report(report), encoding="utf-8")
    out_html.write_text(format_html_report(report), encoding="utf-8")

    print(f"源文件: {report.bugreport_txt}")
    print(f"事件数: {len(report.timeline_events)}")
    print(f"完整区间: {sum(1 for i in report.intervals if not i.incomplete)}")
    print(f"未闭合: {sum(1 for i in report.intervals if i.incomplete)}")
    print(f"JSON: {out_json}")
    print(f"TXT:  {out_txt}")
    print(f"HTML: {out_html}")
    print("")
    print(format_text_report(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
