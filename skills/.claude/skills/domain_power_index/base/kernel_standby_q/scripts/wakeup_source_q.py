#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高通平台 Kernel Pending Wakeup Sources 统计（Top3）。"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime

KEYWORD = "Pending Wakeup Sources:"

_KERNELLOGCAT_RE = re.compile(
    r"^kernellogcat-log\.(\d{8})-(\d{6})(?:\.\w+)?$",
    re.IGNORECASE,
)
_LINE_TIME_RE = re.compile(r"^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2})(?:\.\d+)?")
# [timerfd] 或裸名 IPA_CLIENT_... / rmnet_ctl
_SOURCE_TOKEN_RE = re.compile(r"\[([^\]]+)\]|([A-Za-z_][\w%$.:-]*)")

WAKEUP_FIELDS = (
    "pending_wakeup_sources_top3",
    "pending_wakeup_hit_count",
)


def _setup_utf8_stdio() -> None:
    for stream_name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def parse_kernellogcat_stamp(file_path: str) -> datetime | None:
    name = os.path.basename(file_path)
    m = _KERNELLOGCAT_RE.match(name)
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)}-{m.group(2)}", "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def get_kernellogcat_files(folder_path: str, recursive: bool = True) -> list[str]:
    found: list[str] = []
    if recursive:
        for root, _dirs, files in os.walk(folder_path):
            for file in files:
                if _KERNELLOGCAT_RE.match(file):
                    found.append(os.path.join(root, file))
    else:
        for file in os.listdir(folder_path):
            path = os.path.join(folder_path, file)
            if os.path.isfile(path) and _KERNELLOGCAT_RE.match(file):
                found.append(path)
    return found


def sort_files_by_filename_time(file_paths: list[str]) -> list[str]:
    keyed: list[tuple[datetime, str]] = []
    for path in file_paths:
        stamp = parse_kernellogcat_stamp(path)
        if stamp is None:
            try:
                stamp = datetime.fromtimestamp(os.path.getmtime(path))
            except OSError:
                stamp = datetime.min
        keyed.append((stamp, path))
    keyed.sort(key=lambda x: x[0])
    return [p for _, p in keyed]


def _year_from_files(file_paths: list[str]) -> int:
    for path in file_paths:
        stamp = parse_kernellogcat_stamp(path)
        if stamp is not None:
            return stamp.year
    return datetime.now().year


def _parse_time_literal(value: str | None, base_year: int) -> datetime | None:
    s = (value or "").strip()
    if not s:
        return None
    m = re.match(r"^(\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})(\.\d+)?$", s)
    if m:
        frac = m.group(3) or ""
        new_s = f"{base_year}-{m.group(1)} {m.group(2)}{frac}"
        fmt = "%Y-%m-%d %H:%M:%S.%f" if frac else "%Y-%m-%d %H:%M:%S"
        try:
            return datetime.strptime(new_s, fmt)
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _line_dt(line: str, base_year: int) -> datetime | None:
    m = _LINE_TIME_RE.match(line.strip())
    if not m:
        return None
    return _parse_time_literal(m.group(1), base_year)


def _in_window(
    dt: datetime | None, start_dt: datetime | None, end_dt: datetime | None
) -> bool:
    if dt is None:
        return True
    if start_dt and dt < start_dt:
        return False
    if end_dt and dt > end_dt:
        return False
    return True


def _to_str(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _extract_sources(after_keyword: str) -> list[str]:
    """从 Pending Wakeup Sources: 后的文本提取唤醒源名。"""
    sources: list[str] = []
    for m in _SOURCE_TOKEN_RE.finditer(after_keyword.strip()):
        name = (m.group(1) or m.group(2) or "").strip()
        if not name:
            continue
        # 过滤明显非唤醒源噪声
        if name.lower() in {"pm", "abort", "pending", "wakeup", "sources"}:
            continue
        sources.append(name)
    return sources


def _top_n(counter: dict[str, int], n: int) -> str:
    if not counter:
        return "No"
    items = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
    total = sum(v for _, v in items)
    if total <= 0:
        return "No"
    top = items[:n]
    label = f"Top{n}"
    body = ", ".join(f"{k}({v})" for k, v in top)
    return f"{label}={body}; total={total}"


def _load_lines_from_directory(directory: str) -> tuple[list[str], int, list[str]]:
    files = get_kernellogcat_files(directory, recursive=True)
    if not files:
        raise ValueError(f"未找到 kernellogcat-log.*: {directory}")
    sorted_files = sort_files_by_filename_time(files)
    base_year = _year_from_files(sorted_files)
    lines: list[str] = []
    for path in sorted_files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                lines.extend(f.read().splitlines())
        except OSError:
            continue
    return lines, base_year, sorted_files


def _analyze_lines(
    lines: list[str],
    start_time: str | None,
    end_time: str | None,
    base_year: int,
) -> dict:
    start_dt = _parse_time_literal(start_time, base_year) if start_time else None
    end_dt = _parse_time_literal(end_time, base_year) if end_time else None

    source_count: dict[str, int] = {}
    evidence: list[dict] = []
    hit_count = 0
    first_dt: datetime | None = None
    last_dt: datetime | None = None

    for idx, line in enumerate(lines, 1):
        if KEYWORD not in line:
            continue
        dt = _line_dt(line, base_year)
        if not _in_window(dt, start_dt, end_dt):
            continue

        after = line.split(KEYWORD, 1)[1]
        sources = _extract_sources(after)
        if not sources:
            continue

        hit_count += 1
        if dt is not None:
            if first_dt is None or dt < first_dt:
                first_dt = dt
            if last_dt is None or dt > last_dt:
                last_dt = dt

        for name in sources:
            source_count[name] = source_count.get(name, 0) + 1

        evidence.append(
            {
                "line": idx,
                "time": _to_str(dt),
                "sources": sources,
                "raw_line": line[:400],
            }
        )

    top3 = _top_n(source_count, 3)

    return {
        "summary": {
            "pending_wakeup_sources_top3": top3,
            "pending_wakeup_hit_count": hit_count,
        },
        "stats": {
            "pending_wakeup_hit_count": hit_count,
            "pending_wakeup_sources": {"count": source_count},
            "pending_wakeup_sources_top3": top3,
        },
        "evidence": {
            "pending_wakeup_sources": evidence[:200],  # 限量，避免 JSON 过大
        },
        "meta": {
            "base_year": base_year,
            "start_time": start_time or _to_str(first_dt),
            "end_time": end_time or _to_str(last_dt),
            "keyword": KEYWORD,
        },
    }


def _print_text_report(result: dict) -> None:
    summary = result.get("summary") or {}
    stats = result.get("stats") or {}
    meta = result.get("meta") or {}
    count = (stats.get("pending_wakeup_sources") or {}).get("count") or {}

    print("===== Pending Wakeup Sources Top3 =====")
    print("-" * 80)
    if not count:
        print("（未命中 Pending Wakeup Sources:）")
    else:
        items = sorted(count.items(), key=lambda x: (-x[1], x[0]))
        total = sum(v for _, v in items)
        for i, (name, cnt) in enumerate(items[:3], 1):
            ratio = (cnt / total * 100.0) if total else 0.0
            print(f"{i}. {name}: {cnt} ({ratio:.2f}%)")
        print(f"total_source_hits={total}")
        print(f"pending_line_hits={stats.get('pending_wakeup_hit_count', 0)}")
    print("")

    print("=== 结构化分析摘要(供下游SKILL输入) ===")
    print("[META]")
    print(f"analysis_base_year={meta.get('base_year', '')}")
    print(f"analysis_start={meta.get('start_time') or ''}")
    print(f"analysis_end={meta.get('end_time') or ''}")
    print("")
    print("[SUMMARY]")
    print(f"pending_wakeup_sources_top3={summary.get('pending_wakeup_sources_top3', 'No')}")
    print(f"pending_wakeup_hit_count={summary.get('pending_wakeup_hit_count', 0)}")
    print("")
    print("[STATS]")
    print(f"pending_wakeup_hit_count={stats.get('pending_wakeup_hit_count', 0)}")
    print(f"pending_wakeup_sources_top3={stats.get('pending_wakeup_sources_top3', 'No')}")
    print("")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="高通 Pending Wakeup Sources 统计（kernellogcat-log，Top3）"
    )
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "-d",
        "--directory",
        metavar="DIR",
        help="日志目录（递归查找 kernellogcat-log.*）",
    )
    src.add_argument("--file", dest="file_path", metavar="FILE", help="单个日志文件")
    src.add_argument("--stdin", action="store_true", help="从标准输入读取")
    p.add_argument(
        "-t",
        "--time",
        nargs="*",
        metavar=("START", "END"),
        help="时间窗 YYYY-MM-DD HH:MM:SS；可只给 START 或空 START + END",
    )
    p.add_argument(
        "--format", choices=("text", "json"), default="text", help="输出格式，默认 text"
    )
    p.add_argument(
        "--field",
        action="append",
        dest="fields",
        choices=WAKEUP_FIELDS,
        metavar="FIELD",
        help="仅 json 模式：只输出 summary 指定字段，可重复",
    )
    return p


def _parse_time_args(time_args: list[str] | None) -> tuple[str | None, str | None]:
    if not time_args:
        return None, None
    if len(time_args) == 1:
        return time_args[0], None
    start = time_args[0] or None
    end = time_args[1] if len(time_args) >= 2 else None
    return start, end


def main(argv: list[str] | None = None) -> int:
    _setup_utf8_stdio()
    args = _build_arg_parser().parse_args(argv)
    start_time, end_time = _parse_time_args(args.time)

    try:
        if args.stdin:
            lines = sys.stdin.read().splitlines()
            base_year = datetime.now().year
        elif args.file_path:
            if not os.path.exists(args.file_path):
                print(f"错误：文件不存在: {args.file_path}")
                return 1
            stamp = parse_kernellogcat_stamp(args.file_path)
            base_year = stamp.year if stamp else datetime.now().year
            with open(args.file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.read().splitlines()
        else:
            if not os.path.exists(args.directory):
                print(f"错误：目录不存在: {args.directory}")
                return 1
            if not os.path.isdir(args.directory):
                print(f"错误：不是目录: {args.directory}")
                return 1
            lines, base_year, _files = _load_lines_from_directory(args.directory)
    except Exception as exc:
        print(f"读取日志失败: {exc}")
        return 1

    if not lines:
        print("警告：未读到任何日志行")
        result = _analyze_lines([], start_time, end_time, base_year)
    else:
        result = _analyze_lines(lines, start_time, end_time, base_year)

    if args.format == "json":
        if args.fields:
            output = {
                name: (result.get("summary") or {}).get(name) for name in args.fields
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
        else:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    _print_text_report(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
