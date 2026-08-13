#!/usr/bin/env python3
"""Scan APLog sys/main logs for app download / install signals.

Rules (dou_app_download / dou_2):
1. sys: Usf_Hiber/importantScene + speed > 100，且仅灭屏时段 → uid 下载
2. main: state:DOWNLOADING → 下载包名（不要求灭屏）
3. sys: installation completed for → 安装完成包（不要求灭屏）
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
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

SPEED_RE = re.compile(
    r"Usf_Hiber/importantScene:.*?\buid:(\d+).*?\bspeed\s*:\s*(\d+)",
    re.IGNORECASE,
)
PKG_STATUS_RE = re.compile(
    r"Usf_Hiber/importantScene:.*?packageName=([^\s,]+).*?\buid:(\d+)",
    re.IGNORECASE,
)
START_PROC_RE = re.compile(
    r"Start proc (\d+):([a-zA-Z0-9._]+)/u0a(\d+)\b"
)
# mainlog: ... [Package:com.xxx, ...] state:DOWNLOADING ...
DOWNLOADING_RE = re.compile(
    r"Package:([a-zA-Z0-9._]+)[^\n]*\bstate:DOWNLOADING\b"
    r"|\bstate:DOWNLOADING\b[^\n]*Package:([a-zA-Z0-9._]+)",
    re.IGNORECASE,
)
DOWNLOADING_REASON_RE = re.compile(r"\breason=([^\s,]+)", re.IGNORECASE)
INSTALL_RE = re.compile(
    r"installation completed for package:([a-zA-Z0-9_]+(?:\.[a-zA-Z0-9_]+)+)",
    re.IGNORECASE,
)
TS_RE = re.compile(r"^(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}(?:\.\d+)?)")

# 灭屏 / 亮屏（仅用于 Usf_Hiber 过滤）
SCREEN_OFF_RE = re.compile(
    r"PowerManagerService:\s+(?:Going to sleep|Sleeping)\b",
    re.IGNORECASE,
)
SCREEN_ON_RE = re.compile(
    r"PowerManagerService:\s+Waking up from Asleep\b"
    r"|PowerGroup:\s+Waking up power group from Asleep\b",
    re.IGNORECASE,
)

DEFAULT_GAP_SEC = 120
MIN_RANGE_SEC = 3  # 下载时段时长 < 3s 不计
SPEED_MIN = 100  # Usf_Hiber：仅 speed > 100


def _iter_files(root: Path, prefixes: Tuple[str, ...]) -> List[Path]:
    files: List[Path] = []
    if root.is_file():
        name = root.name
        if any(name.startswith(p) for p in prefixes):
            return [root]
        return []
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in filenames:
            if any(fn.startswith(p) for p in prefixes):
                files.append(Path(dirpath) / fn)
    files.sort(key=lambda p: str(p))
    return files


def find_aplog_roots(path: Path) -> List[Path]:
    path = path.resolve() if path.exists() else path
    if path.is_file():
        return [path.parent]
    aplogs = [p for p in path.rglob("APLog_*") if p.is_dir()]
    if aplogs:
        return sorted(aplogs)
    if any(path.glob("sys_log*")) or any(path.glob("main_log*")):
        return [path]
    return [path]


def _read_lines(fp: Path) -> Iterable[str]:
    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            yield line


def parse_ts(line: str) -> Optional[datetime]:
    m = TS_RE.match(line)
    if not m:
        return None
    raw = m.group(1)
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"2000-{raw}", fmt)
        except ValueError:
            continue
    return None


def fmt_ts(dt: Optional[datetime]) -> Optional[str]:
    """展示用时间：月-日 时:分:秒（不含毫秒）。"""
    if dt is None:
        return None
    return dt.strftime("%m-%d %H:%M:%S")


def fmt_time_range(start: Optional[str], end: Optional[str]) -> str:
    if not start and not end:
        return ""
    if start == end or not end:
        return f"时间 {start}"
    return f"开始时间 {start}  结束时间 {end}"


def _parse_disp_ts(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(f"2000-{s}", fmt)
        except ValueError:
            continue
    return None


def build_screen_transitions(
    events: List[Tuple[datetime, str]]
) -> List[Tuple[datetime, bool]]:
    """(ts, is_off) 按时间排序；同秒内 off 优先于 on。"""
    if not events:
        return []
    ranked = sorted(events, key=lambda x: (x[0], 0 if x[1] == "off" else 1))
    out: List[Tuple[datetime, bool]] = []
    for ts, kind in ranked:
        is_off = kind == "off"
        if out and out[-1][0] == ts and out[-1][1] == is_off:
            continue
        if out and out[-1][1] == is_off:
            continue
        out.append((ts, is_off))
    return out


def is_screen_off_at(
    ts: datetime, transitions: List[Tuple[datetime, bool]]
) -> bool:
    """未知亮灭屏时按亮屏处理（不计入 Usf_Hiber 下载）。"""
    if not transitions:
        return False
    state: Optional[bool] = None
    for t, is_off in transitions:
        if t <= ts:
            state = is_off
        else:
            break
    return bool(state)


def screen_off_intervals(
    transitions: List[Tuple[datetime, bool]]
) -> List[dict]:
    """灭屏区间列表（供结果透明展示）。"""
    if not transitions:
        return []
    intervals: List[dict] = []
    cur_off: Optional[datetime] = None
    for ts, is_off in transitions:
        if is_off:
            if cur_off is None:
                cur_off = ts
        else:
            if cur_off is not None:
                intervals.append(
                    {
                        "start": fmt_ts(cur_off),
                        "end": fmt_ts(ts),
                        "duration_sec": max(
                            0, int((ts - cur_off).total_seconds())
                        ),
                    }
                )
                cur_off = None
    if cur_off is not None:
        intervals.append(
            {
                "start": fmt_ts(cur_off),
                "end": None,
                "duration_sec": None,
                "open_ended": True,
            }
        )
    return intervals


def merge_ranges(
    events: List[Tuple[datetime, int]], gap_sec: int
) -> List[dict]:
    if not events:
        return []
    events = sorted(events, key=lambda x: x[0])
    ranges: List[dict] = []
    start, end = events[0][0], events[0][0]
    hits = 1
    max_speed = events[0][1]
    gap = timedelta(seconds=gap_sec)
    for ts, speed in events[1:]:
        if ts - end <= gap:
            end = ts
            hits += 1
            max_speed = max(max_speed, speed)
        else:
            ranges.append(
                {
                    "start": fmt_ts(start),
                    "end": fmt_ts(end),
                    "hits": hits,
                    "max_speed": max_speed,
                    "duration_sec": max(0, int((end - start).total_seconds())),
                }
            )
            start, end = ts, ts
            hits = 1
            max_speed = speed
    ranges.append(
        {
            "start": fmt_ts(start),
            "end": fmt_ts(end),
            "hits": hits,
            "max_speed": max_speed,
            "duration_sec": max(0, int((end - start).total_seconds())),
        }
    )
    return ranges


def merge_pkg_ranges(
    events: List[Tuple[datetime, str]], gap_sec: int
) -> List[dict]:
    """合并 state:DOWNLOADING 命中（value 为 reason）。"""
    if not events:
        return []
    events = sorted(events, key=lambda x: x[0])
    ranges: List[dict] = []
    start, end = events[0][0], events[0][0]
    hits = 1
    reasons = {events[0][1]} if events[0][1] else set()
    gap = timedelta(seconds=gap_sec)
    for ts, reason in events[1:]:
        if ts - end <= gap:
            end = ts
            hits += 1
            if reason:
                reasons.add(reason)
        else:
            ranges.append(
                {
                    "start": fmt_ts(start),
                    "end": fmt_ts(end),
                    "hits": hits,
                    "reasons": sorted(reasons),
                    "duration_sec": max(0, int((end - start).total_seconds())),
                }
            )
            start, end = ts, ts
            hits = 1
            reasons = {reason} if reason else set()
    ranges.append(
        {
            "start": fmt_ts(start),
            "end": fmt_ts(end),
            "hits": hits,
            "reasons": sorted(reasons),
            "duration_sec": max(0, int((end - start).total_seconds())),
        }
    )
    return ranges


def filter_short_ranges(ranges: List[dict], min_sec: int = MIN_RANGE_SEC) -> List[dict]:
    """丢弃时长 < min_sec 的下载时段。"""
    return [r for r in ranges if int(r.get("duration_sec") or 0) >= min_sec]


def build_narrative(result: dict, top_n: int = 0) -> dict:
    """结构化结论：短摘要 + 全量时段表。"""
    traffic = result["traffic_speed_nonzero"]["items"]
    main_dl = result.get("main_downloading") or result.get("finsky_running_nonzero") or {}
    main_items = main_dl.get("items") or []
    installs = result["installations"]
    min_sec = int(result.get("min_range_sec") or MIN_RANGE_SEC)
    speed_min = int(result.get("speed_min") or SPEED_MIN)
    paragraphs: List[str] = []

    if not result["download_active"] and not installs:
        paragraphs.append(
            f"未发现应用下载（灭屏 Usf_Hiber speed>{speed_min} / mainlog state:DOWNLOADING）与安装完成记录。"
        )
        return {
            "paragraphs": paragraphs,
            "top_downloads": [],
            "range_rows": [],
            "finsky_rows": [],
            "install_notes": [],
        }

    apps = traffic if not top_n else traffic[:top_n]
    if traffic:
        overall_first = min(x["first_ts"] for x in traffic if x.get("first_ts"))
        overall_last = max(x["last_ts"] for x in traffic if x.get("last_ts"))
        total_ranges = sum(int(x.get("range_count") or 0) for x in traffic)
        paragraphs.append(
            f"【下载总览·灭屏】Usf_Hiber speed>{speed_min}（单段≥{min_sec}s）｜"
            f"应用 {result['traffic_speed_nonzero']['uid_count']} 个｜"
            f"有效时段 {total_ranges} 段｜命中 {result['traffic_speed_nonzero']['total_hits']} 次｜"
            f"最早 {overall_first}｜最晚 {overall_last}"
        )
    else:
        paragraphs.append(
            f"【下载总览·灭屏】未发现有效 Usf_Hiber 下载（speed>{speed_min} 且灭屏，单段≥{min_sec}s）。"
        )

    range_rows: List[dict] = []
    top_downloads = []
    for item in apps:
        pkg = item.get("package") or "未知包名"
        pids = item.get("pids") or []
        ranges = item.get("time_ranges") or []
        top_downloads.append(
            {
                "package": pkg,
                "uid": item["uid"],
                "pids": pids,
                "first_ts": item["first_ts"],
                "last_ts": item["last_ts"],
                "max_speed": item["max_speed"],
                "hits": item["hits"],
                "range_count": item["range_count"],
                "time_ranges": ranges,
            }
        )
        for i, r in enumerate(ranges, 1):
            range_rows.append(
                {
                    "package": pkg,
                    "uid": item["uid"],
                    "pid": "、".join(pids) if pids else "",
                    "seg": i,
                    "start": r.get("start"),
                    "end": r.get("end"),
                    "max_speed": r.get("max_speed"),
                    "hits": r.get("hits"),
                }
            )

    finsky_rows: List[dict] = []
    if main_items:
        paragraphs.append(
            f"【商店下载】mainlog state:DOWNLOADING 有效包 "
            f"{main_dl.get('package_count', len(main_items))} 个｜"
            f"时段 {sum(len(x.get('time_ranges') or []) for x in main_items)} 段"
        )
        for item in main_items:
            for r in item.get("time_ranges") or []:
                finsky_rows.append(
                    {
                        "package": item.get("package"),
                        "download_id": ",".join(r.get("reasons") or []) or "-",
                        "start": r.get("start"),
                        "end": r.get("end"),
                        "max_progress": "-",
                        "hits": r.get("hits"),
                        "reasons": r.get("reasons") or [],
                    }
                )
    else:
        paragraphs.append("【商店下载】mainlog 无 state:DOWNLOADING 有效记录")

    install_notes = []
    if not installs:
        paragraphs.append("【安装】无 installation completed for 记录")
    else:
        for inst in installs:
            its = _parse_disp_ts(inst["ts"])
            overlap_pkgs: List[str] = []
            if its:
                for item in traffic:
                    a = _parse_disp_ts(item["first_ts"])
                    b = _parse_disp_ts(item["last_ts"])
                    if a and b and a <= its <= b:
                        overlap_pkgs.append(item.get("package") or item["uid"])
                for item in main_items:
                    a = _parse_disp_ts(item["first_ts"])
                    b = _parse_disp_ts(item["last_ts"])
                    if a and b and a <= its <= (b + timedelta(minutes=5)):
                        overlap_pkgs.append(item.get("package") or "")
            overlap_pkgs = sorted({p for p in overlap_pkgs if p})
            install_notes.append(
                {
                    "ts": inst["ts"],
                    "package": inst["package"],
                    "near_download_packages": overlap_pkgs,
                }
            )
            rel = f"｜关联下载 {', '.join(overlap_pkgs)}" if overlap_pkgs else ""
            paragraphs.append(f"【安装】{inst['ts']}  完成 {inst['package']}{rel}")

    paragraphs.append(
        f"【说明】Usf_Hiber 仅计灭屏且 speed>{speed_min}；"
        f"mainlog 用 state:DOWNLOADING 取包名（不限亮灭屏）；"
        f"uid=应用身份；pid=Start proc；单段≥{min_sec}s。"
    )
    return {
        "paragraphs": paragraphs,
        "top_downloads": top_downloads,
        "range_rows": range_rows,
        "finsky_rows": finsky_rows,
        "install_notes": install_notes,
    }


def _pad(s: object, width: int) -> str:
    text = "" if s is None else str(s)
    w = 0
    for ch in text:
        w += 2 if ord(ch) > 127 else 1
    if w >= width:
        return text
    return text + (" " * (width - w))


def analyze(
    aplog_dirs: List[Path],
    gap_sec: int = DEFAULT_GAP_SEC,
    min_range_sec: int = MIN_RANGE_SEC,
    speed_min: int = SPEED_MIN,
) -> dict:
    uid_events: Dict[str, List[Tuple[datetime, int]]] = defaultdict(list)
    uid2pkg: Dict[str, str] = {}
    uid2pids: Dict[str, set] = defaultdict(set)
    downloading_events: Dict[str, List[Tuple[datetime, str]]] = defaultdict(list)
    install_events: List[Tuple[datetime, str]] = []
    screen_events: List[Tuple[datetime, str]] = []
    speed_hits_raw = 0
    speed_hits_screen_off = 0

    sys_files: List[Path] = []
    main_files: List[Path] = []
    for d in aplog_dirs:
        sys_files.extend(_iter_files(d, ("sys_log",)))
        main_files.extend(_iter_files(d, ("main_log",)))

    def _note_start_proc(line: str) -> None:
        m = START_PROC_RE.search(line)
        if not m:
            return
        pid, pkg, appid = m.group(1), m.group(2), m.group(3)
        uid = str(10000 + int(appid))
        uid2pkg.setdefault(uid, pkg)
        uid2pids[uid].add(pid)

    # 先扫灭屏/亮屏，再过滤 speed
    pending_speed: List[Tuple[datetime, str, int]] = []

    for fp in sys_files:
        for line in _read_lines(fp):
            if "PowerManagerService:" in line or "PowerGroup:" in line:
                ts = parse_ts(line)
                if ts:
                    if SCREEN_OFF_RE.search(line):
                        screen_events.append((ts, "off"))
                    elif SCREEN_ON_RE.search(line):
                        screen_events.append((ts, "on"))
            if "Usf_Hiber/importantScene" in line:
                m = PKG_STATUS_RE.search(line)
                if m:
                    uid2pkg[m.group(2)] = m.group(1)
                m = SPEED_RE.search(line)
                if m:
                    uid, speed = m.group(1), int(m.group(2))
                    if speed > speed_min:
                        ts = parse_ts(line)
                        if ts:
                            speed_hits_raw += 1
                            pending_speed.append((ts, uid, speed))
            elif "Start proc " in line:
                _note_start_proc(line)
            if "installation completed for" in line:
                m = INSTALL_RE.search(line)
                if m:
                    ts = parse_ts(line)
                    if ts:
                        install_events.append((ts, m.group(1)))

    transitions = build_screen_transitions(screen_events)
    for ts, uid, speed in pending_speed:
        if is_screen_off_at(ts, transitions):
            speed_hits_screen_off += 1
            uid_events[uid].append((ts, speed))

    for fp in main_files:
        for line in _read_lines(fp):
            if "state:DOWNLOADING" in line:
                m = DOWNLOADING_RE.search(line)
                if m:
                    pkg = m.group(1) or m.group(2)
                    ts = parse_ts(line)
                    if pkg and ts:
                        reason_m = DOWNLOADING_REASON_RE.search(line)
                        reason = reason_m.group(1) if reason_m else ""
                        downloading_events[pkg].append((ts, reason))
            elif "Start proc " in line:
                _note_start_proc(line)

    traffic = []
    for uid, events in uid_events.items():
        ranges = filter_short_ranges(merge_ranges(events, gap_sec), min_range_sec)
        if not ranges:
            continue
        hits = sum(int(r["hits"]) for r in ranges)
        max_speed = max(int(r["max_speed"]) for r in ranges)
        pids = sorted(uid2pids.get(uid, set()), key=lambda x: int(x))
        traffic.append(
            {
                "uid": uid,
                "package": uid2pkg.get(uid),
                "pids": pids,
                "hits": hits,
                "max_speed": max_speed,
                "first_ts": ranges[0]["start"],
                "last_ts": ranges[-1]["end"],
                "time_ranges": ranges,
                "range_count": len(ranges),
                "screen": "off",
            }
        )
    traffic.sort(key=lambda x: -x["hits"])

    main_out = []
    for pkg, events in downloading_events.items():
        ranges = filter_short_ranges(merge_pkg_ranges(events, gap_sec), min_range_sec)
        if not ranges:
            # DOWNLOADING 可能只有单点命中：保留 duration=0 的单点（仍展示包名）
            if events:
                evs = sorted(events, key=lambda x: x[0])
                reasons = sorted({r for _, r in evs if r})
                ranges = [
                    {
                        "start": fmt_ts(evs[0][0]),
                        "end": fmt_ts(evs[-1][0]),
                        "hits": len(evs),
                        "reasons": reasons,
                        "duration_sec": max(
                            0, int((evs[-1][0] - evs[0][0]).total_seconds())
                        ),
                    }
                ]
            else:
                continue
        main_out.append(
            {
                "package": pkg,
                "hits": sum(int(r["hits"]) for r in ranges),
                "reasons": sorted(
                    {rr for r in ranges for rr in (r.get("reasons") or [])}
                ),
                "first_ts": ranges[0]["start"],
                "last_ts": ranges[-1]["end"],
                "time_ranges": ranges,
            }
        )
    main_out.sort(key=lambda x: -x["hits"])

    installs = [
        {"package": pkg, "ts": fmt_ts(ts)}
        for ts, pkg in sorted(install_events, key=lambda x: x[0])
    ]

    main_block = {
        "package_count": len(main_out),
        "total_hits": sum(x["hits"] for x in main_out),
        "items": main_out,
        "keyword": "state:DOWNLOADING",
    }

    result = {
        "aplog_dirs": [str(p) for p in aplog_dirs],
        "sys_log_files": len(sys_files),
        "main_log_files": len(main_files),
        "gap_sec": gap_sec,
        "min_range_sec": min_range_sec,
        "speed_min": speed_min,
        "screen_off_only_for_usf": True,
        "screen_transitions": len(transitions),
        "screen_off_intervals": screen_off_intervals(transitions),
        "speed_hits_raw_gt_min": speed_hits_raw,
        "speed_hits_screen_off": speed_hits_screen_off,
        "download_active": len(traffic) > 0 or len(main_out) > 0,
        "traffic_speed_nonzero": {
            "uid_count": len(traffic),
            "total_hits": sum(x["hits"] for x in traffic),
            "items": traffic,
            "rule": f"Usf_Hiber speed>{speed_min} AND screen_off",
        },
        "main_downloading": main_block,
        # 兼容旧 Look / 产物字段名
        "finsky_running_nonzero": main_block,
        "installations": installs,
        "uid_package_map_size": len(uid2pkg),
    }
    result["narrative"] = build_narrative(result)
    return result


def format_text(result: dict) -> str:
    lines = []
    nar = result.get("narrative") or {}
    min_sec = int(result.get("min_range_sec") or MIN_RANGE_SEC)
    speed_min = int(result.get("speed_min") or SPEED_MIN)
    lines.append("=== 结论摘要 ===")
    for p in nar.get("paragraphs") or []:
        lines.append(p)
    lines.append("")

    lines.append(
        f"=== 灭屏 Usf_Hiber 下载（speed>{speed_min}，单段≥{min_sec}s）==="
    )
    rows = nar.get("range_rows") or []
    if not rows:
        lines.append("(无)")
    else:
        header = (
            f"{_pad('#', 4)} {_pad('包名', 36)} {_pad('uid', 7)} "
            f"{_pad('开始时间', 16)} {_pad('结束时间', 16)} "
            f"{_pad('max_speed', 10)} {_pad('hits', 6)}"
        )
        lines.append(header)
        lines.append("-" * len(header))
        for idx, r in enumerate(rows, 1):
            lines.append(
                f"{_pad(idx, 4)} {_pad(r.get('package'), 36)} {_pad(r.get('uid'), 7)} "
                f"{_pad(r.get('start'), 16)} {_pad(r.get('end'), 16)} "
                f"{_pad(r.get('max_speed'), 10)} {_pad(r.get('hits'), 6)}"
            )
    lines.append("")

    lines.append("=== 按应用分组（灭屏 Usf_Hiber）===")
    apps = nar.get("top_downloads") or result["traffic_speed_nonzero"]["items"]
    if not apps:
        lines.append("(无)")
    for item in apps:
        pkg = item.get("package") or "?"
        pids = item.get("pids") or []
        pid_txt = "、".join(pids) if pids else "-"
        lines.append("")
        lines.append(
            f"■ {pkg} ｜ uid={item.get('uid')} ｜ pid={pid_txt} ｜ "
            f"峰值speed={item.get('max_speed')} ｜ 有效段={item.get('range_count')}"
        )
        lines.append(
            f"  {_pad('段', 4)} {_pad('开始时间', 16)} {_pad('结束时间', 16)} "
            f"{_pad('max_speed', 10)} {_pad('hits', 6)}"
        )
        for i, r in enumerate(item.get("time_ranges") or [], 1):
            lines.append(
                f"  {_pad(i, 4)} {_pad(r.get('start'), 16)} {_pad(r.get('end'), 16)} "
                f"{_pad(r.get('max_speed'), 10)} {_pad(r.get('hits'), 6)}"
            )

    lines.append("")
    lines.append("=== mainlog state:DOWNLOADING ===")
    frows = nar.get("finsky_rows") or []
    if not frows:
        lines.append("(无)")
    else:
        lines.append(
            f"{_pad('包名', 36)} {_pad('开始时间', 16)} {_pad('结束时间', 16)} "
            f"{_pad('reason', 20)} {_pad('hits', 6)}"
        )
        for r in frows:
            reason = r.get("download_id") or ",".join(r.get("reasons") or []) or "-"
            lines.append(
                f"{_pad(r.get('package'), 36)} {_pad(r.get('start'), 16)} "
                f"{_pad(r.get('end'), 16)} {_pad(reason, 20)} {_pad(r.get('hits'), 6)}"
            )

    lines.append("")
    lines.append("=== 安装完成 ===")
    installs = result.get("installations") or []
    if not installs:
        lines.append("(无)")
    else:
        for item in installs:
            lines.append(f"  时间 {item['ts']}  包名 {item['package']}")

    lines.append("")
    lines.append("=== 运行参数 ===")
    lines.append(
        f"speed_min={speed_min}  gap_sec={result.get('gap_sec')}  "
        f"min_range_sec={min_sec}  screen_off_only_for_usf=True  "
        f"sys_log={result.get('sys_log_files')}  main_log={result.get('main_log_files')}  "
        f"speed_raw={result.get('speed_hits_raw_gt_min')}  "
        f"speed_screen_off={result.get('speed_hits_screen_off')}  "
        f"screen_transitions={result.get('screen_transitions')}"
    )
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    _setup_utf8_stdio()
    parser = argparse.ArgumentParser(
        description="Detect app download/install from sys_log / main_log"
    )
    parser.add_argument(
        "-d",
        "--directory",
        required=True,
        help="high root / phone_logs / mobilelog / APLog_* directory",
    )
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("-o", "--output", help="optional output file path")
    parser.add_argument(
        "--gap-sec",
        type=int,
        default=DEFAULT_GAP_SEC,
        help=f"merge hits into one range if gap <= this (default {DEFAULT_GAP_SEC})",
    )
    parser.add_argument(
        "--min-sec",
        type=int,
        default=MIN_RANGE_SEC,
        help=f"ignore Usf_Hiber ranges shorter than this (default {MIN_RANGE_SEC})",
    )
    parser.add_argument(
        "--speed-min",
        type=int,
        default=SPEED_MIN,
        help=f"Usf_Hiber: only count speed > this (default {SPEED_MIN})",
    )
    args = parser.parse_args(argv)

    root = Path(args.directory)
    if not root.exists():
        print(f"ERROR: path not found: {root}", file=sys.stderr)
        return 2

    result = analyze(
        find_aplog_roots(root),
        gap_sec=args.gap_sec,
        min_range_sec=args.min_sec,
        speed_min=args.speed_min,
    )
    text = (
        format_text(result)
        if args.format == "text"
        else json.dumps(result, ensure_ascii=False, indent=2)
    )

    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        print(f"wrote {out}")
    else:
        ext = "txt" if args.format == "text" else "json"
        out = Path.cwd() / f"download_traffic_result.{ext}"
        out.write_text(text + ("\n" if not text.endswith("\n") else ""), encoding="utf-8")
        print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
