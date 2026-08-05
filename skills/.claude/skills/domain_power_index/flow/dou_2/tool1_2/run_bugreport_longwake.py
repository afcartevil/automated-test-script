#!/usr/bin/env python3
"""DOU 流程第 9 步（补充）：高/低功耗全部 longwake 时间轴。

产物（各 side 根目录各一份）：
  - <root>/bugreport_longwake_result.json
  - <bugreport目录>/bugreport_longwake.{json,txt,html}
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _setup_utf8_stdio() -> None:
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _module_scripts() -> Path:
    return Path(__file__).resolve().parent.parent / "bugreport_audiomix" / "scripts"


def _process_side(
    root: str,
    side: str,
    *,
    bugreport: str,
    output_json: str,
) -> int:
    scripts = _module_scripts()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from parse_audiomix import find_bugreport_dir  # noqa: E402
    from parse_longwake import (  # noqa: E402
        analyze_bugreport,
        format_html_report,
        format_text_report,
        report_to_json,
    )

    label = "高功耗" if side == "high" else "低功耗"
    print(f"=== {label} ({side}): {root} ===")

    if bugreport.strip():
        bugreport_src = Path(bugreport.strip())
    else:
        bugreport_src = find_bugreport_dir(Path(root))
        if bugreport_src is None:
            skipped = {
                "high": root,
                "side": side,
                "skill": "flow_power_bugreport_longwake",
                "step": "dou_2_bugreport_longwake",
                "skipped": True,
                "reason": "未在 phone_logs 下找到 bugreport txt",
                "generated_at": datetime.now(timezone.utc).astimezone().isoformat(
                    timespec="seconds"
                ),
            }
            out_json = output_json.strip() or os.path.join(root, "bugreport_longwake_result.json")
            Path(out_json).write_text(
                json.dumps(skipped, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            print(f"skip: 未找到 bugreport under {root}")
            print(f"wrote {out_json}")
            return 0

    report = analyze_bugreport(bugreport_src)
    bugreport_dir = Path(report.bugreport_txt).parent

    detail_json = bugreport_dir / "bugreport_longwake.json"
    detail_txt = bugreport_dir / "bugreport_longwake.txt"
    detail_html = bugreport_dir / "bugreport_longwake.html"

    payload = report_to_json(report)
    payload["meta"] = {
        "tool": "tool1_2/run_bugreport_longwake.py",
        "side": side,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    detail_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_txt.write_text(format_text_report(report), encoding="utf-8")
    detail_html.write_text(format_html_report(report), encoding="utf-8")

    dou_result = {
        "high": root,
        "side": side,
        "skill": "flow_power_bugreport_longwake",
        "step": "dou_2_bugreport_longwake",
        "skipped": False,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "bugreport_txt": report.bugreport_txt,
        "bugreport_dir": str(bugreport_dir),
        "event_count": len(report.timeline_events),
        "interval_count": sum(1 for i in report.intervals if not i.incomplete),
        "incomplete_count": sum(1 for i in report.intervals if i.incomplete),
        "by_category_totals": report.by_category_totals,
        "top_owners": list(report.by_owner_totals.values())[:8],
        "artifacts": {
            "json": str(detail_json),
            "txt": str(detail_txt),
            "html": str(detail_html),
        },
    }

    out_json = output_json.strip() or os.path.join(root, "bugreport_longwake_result.json")
    Path(out_json).write_text(
        json.dumps(dou_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"源文件: {report.bugreport_txt}")
    print(f"事件数: {len(report.timeline_events)}")
    print(f"完整区间: {dou_result['interval_count']}")
    print(f"详细 JSON: {detail_json}")
    print(f"详细 HTML: {detail_html}")
    print(f"wrote {out_json}")
    return 0


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="DOU：扫描高/低功耗 phone_logs bugreport，解析全部 longwake 时间轴"
    )
    parser.add_argument("high", help="高功耗目录")
    parser.add_argument(
        "--low",
        default="",
        help="低功耗目录（推荐必传；默认从 prepare/scene_compare/power_analysis JSON 回退）",
    )
    parser.add_argument(
        "--bugreport",
        default="",
        help="显式指定 bugreport 目录或 txt（仅作用于 high；low 仍自动搜索）",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="高功耗根目录 JSON（默认 <high>/bugreport_longwake_result.json）",
    )
    args = parser.parse_args()

    high = os.path.abspath(str(args.high).strip())
    if not os.path.isdir(high):
        print(f"高功耗目录无效：{high}", file=sys.stderr)
        return 1

    scripts = _module_scripts()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from parse_audiomix import resolve_dou_side_dirs  # noqa: E402

    rc = 0
    for root, side in resolve_dou_side_dirs(high, args.low):
        if not os.path.isdir(root):
            print(f"目录无效（{side}）：{root}", file=sys.stderr)
            rc = 1
            continue
        bugreport = args.bugreport if side == "high" else ""
        out_json = args.output_json if side == "high" else ""
        rc |= _process_side(
            root,
            side,
            bugreport=bugreport,
            output_json=out_json,
        )
        print("")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
