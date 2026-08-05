#!/usr/bin/env python3
"""DOU 流程第 9 步：高/低功耗 Bugreport AudioMix 持锁时间轴。

产物（各 side 根目录各一份）：
  - <root>/bugreport_audiomix_result.json
  - <root>/bugreport_audiomix_result.txt
  - <bugreport目录>/bugreport_audiomix.{json,txt,html}（详细时间轴）
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


def _under_root(path: str, root: str) -> bool:
    ap = os.path.abspath(path)
    r = os.path.abspath(root)
    try:
        return os.path.commonpath([os.path.normcase(r), os.path.normcase(ap)]) == os.path.normcase(r)
    except ValueError:
        return os.path.normcase(ap).startswith(os.path.normcase(r) + os.sep)


def _process_side(
    root: str,
    side: str,
    *,
    bugreport: str,
    output_json: str,
    output_txt: str,
) -> int:
    scripts = _module_scripts()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))

    from parse_audiomix import (  # noqa: E402
        analyze_bugreport,
        build_dou_result,
        find_bugreport_dir,
        format_dou_summary_text,
        format_html_report,
        format_text_report,
        report_to_json,
    )
    from scene_align import annotate_report  # noqa: E402

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
                "skill": "flow_power_bugreport_audiomix",
                "step": "dou_2_bugreport_audiomix",
                "skipped": True,
                "reason": "未在 phone_logs 下找到 bugreport txt",
                "generated_at": datetime.now(timezone.utc).astimezone().isoformat(
                    timespec="seconds"
                ),
            }
            out_json = output_json.strip() or os.path.join(root, "bugreport_audiomix_result.json")
            out_txt = output_txt.strip() or os.path.join(root, "bugreport_audiomix_result.txt")
            Path(out_json).write_text(
                json.dumps(skipped, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            Path(out_txt).write_text(
                f"未找到 bugreport，本步已跳过（{label}）。\n", encoding="utf-8"
            )
            print(f"skip: 未找到 bugreport under {root}")
            print(f"wrote {out_json}")
            print(f"wrote {out_txt}")
            return 0

    report = analyze_bugreport(bugreport_src)
    report = annotate_report(report, Path(root))
    bugreport_dir = Path(report.bugreport_txt).parent

    detail_json = bugreport_dir / "bugreport_audiomix.json"
    detail_txt = bugreport_dir / "bugreport_audiomix.txt"
    detail_html = bugreport_dir / "bugreport_audiomix.html"

    payload = report_to_json(report)
    payload["meta"] = {
        "tool": "tool1_2/run_bugreport_audiomix.py",
        "side": side,
        "parsed_at": datetime.now(timezone.utc).isoformat(),
    }
    detail_json.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    detail_txt.write_text(format_text_report(report), encoding="utf-8")
    detail_html.write_text(format_html_report(report), encoding="utf-8")

    artifacts = {
        "json": str(detail_json),
        "txt": str(detail_txt),
        "html": str(detail_html),
    }
    dou_result = build_dou_result(report, root, bugreport_dir, artifacts, side=side)
    dou_result["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )

    out_json = output_json.strip() or os.path.join(root, "bugreport_audiomix_result.json")
    out_txt = output_txt.strip() or os.path.join(root, "bugreport_audiomix_result.txt")

    for label_name, path in (("json", out_json), ("txt", out_txt)):
        if not _under_root(path, root):
            print(f"拒绝写入根目录以外路径（{label_name}）：{path}", file=sys.stderr)
            return 2

    summary_text = format_dou_summary_text(dou_result)
    Path(out_json).write_text(
        json.dumps(dou_result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    Path(out_txt).write_text(summary_text, encoding="utf-8")

    print(f"源文件: {report.bugreport_txt}")
    print(f"事件数: {len(report.timeline_events)}")
    print(f"完整区间: {dou_result['interval_count']}")
    print(f"DOU场景: {dou_result.get('scene_count', 0)} | 异常: {dou_result.get('abnormal_count', 0)}")
    print(f"详细 JSON: {detail_json}")
    print(f"详细 HTML: {detail_html}")
    print(f"wrote {out_json}")
    print(f"摘要 TXT: {out_txt}")
    return 0


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="DOU：扫描高/低功耗 phone_logs bugreport，解析 AudioMix 持锁时间轴"
    )
    parser.add_argument("high", help="高功耗目录（DOU高功耗文件夹下的项目根）")
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
        help="高功耗根目录 JSON（默认 <high>/bugreport_audiomix_result.json）",
    )
    parser.add_argument(
        "--output-txt",
        default="",
        help="高功耗根目录 TXT（默认 <high>/bugreport_audiomix_result.txt）",
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
        out_txt = args.output_txt if side == "high" else ""
        rc |= _process_side(
            root,
            side,
            bugreport=bugreport,
            output_json=out_json,
            output_txt=out_txt,
        )
        print("")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
