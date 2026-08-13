#!/usr/bin/env python3
"""DOU 全流程最后一步：高功耗目录应用下载/安装检测。

产物一律落在高功耗根目录（勿写本地 temp）：
  - app_download_result.json
  - app_download_result.txt

工作区根解析见 analysis/base/lib/repo_paths.py。
"""

from __future__ import annotations
def _setup_utf8_stdio() -> None:
    import sys
    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


def _app_download_scripts() -> Path:
    return Path(__file__).resolve().parent.parent / "app_download" / "scripts"


def main() -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="扫描高功耗 phone_logs，判定应用下载/安装并落盘结论"
    )
    parser.add_argument("high", help="高功耗目录（DOU高功耗文件夹下的项目根）")
    parser.add_argument(
        "--gap-sec",
        type=int,
        default=120,
        help="命中合并间隔秒（默认 120）",
    )
    parser.add_argument(
        "--min-sec",
        type=int,
        default=3,
        help="Usf_Hiber 下载时段时长小于该秒数不计（默认 3）",
    )
    parser.add_argument(
        "--speed-min",
        type=int,
        default=100,
        help="Usf_Hiber 仅统计 speed 大于该值（默认 100）",
    )
    parser.add_argument(
        "--output-json",
        default="",
        help="JSON 输出路径（默认 <high>/app_download_result.json）",
    )
    parser.add_argument(
        "--output-txt",
        default="",
        help="TXT 输出路径（默认 <high>/app_download_result.txt）",
    )
    args = parser.parse_args()

    high = os.path.abspath(str(args.high).strip())
    if not os.path.isdir(high):
        print(f"高功耗目录无效：{high}", file=sys.stderr)
        return 1

    scripts = _app_download_scripts()
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from download_traffic import analyze, find_aplog_roots, format_text  # noqa: E402

    aplogs = find_aplog_roots(Path(high))
    result = analyze(
        aplogs,
        gap_sec=int(args.gap_sec),
        min_range_sec=int(args.min_sec),
        speed_min=int(args.speed_min),
    )
    result["high"] = high
    result["generated_at"] = datetime.now(timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )
    result["skill"] = "flow_power_app_download"
    result["step"] = "dou_2_final_app_download"

    out_json = args.output_json.strip() or os.path.join(high, "app_download_result.json")
    out_txt = args.output_txt.strip() or os.path.join(high, "app_download_result.txt")

    def _under_high(path: str) -> bool:
        ap = os.path.abspath(path)
        h = os.path.abspath(high)
        try:
            return os.path.commonpath([os.path.normcase(h), os.path.normcase(ap)]) == os.path.normcase(h)
        except ValueError:
            return os.path.normcase(ap).startswith(os.path.normcase(h) + os.sep)

    for label, path in (("json", out_json), ("txt", out_txt)):
        if not _under_high(path):
            print(
                f"拒绝写入 high 以外路径（{label}）：{path}\n必须落在：{high}",
                file=sys.stderr,
            )
            return 2

    text = format_text(result)
    Path(out_json).parent.mkdir(parents=True, exist_ok=True)
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    with open(out_txt, "w", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")

    nar = (result.get("narrative") or {}).get("paragraphs") or []
    print(f"wrote {out_json}")
    print(f"wrote {out_txt}")
    print(f"download_active={result.get('download_active')} narrative_lines={len(nar)}")
    if nar:
        print("--- 结论摘要 ---")
        for line in nar[:6]:
            print(line)
        if len(nar) > 6:
            print(f"... 另有 {len(nar) - 6} 行，见 txt/json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
