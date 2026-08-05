#!/usr/bin/env python3
"""Parse bugreport txt for AudioMix wake lock / longwake timeline."""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

TS_RE = re.compile(r"(\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})")
# +longwake=u0a346:"AudioMix"  /  -longwake=...  /  longwake=... (already held)
EVENT_RE = re.compile(
    r"(?P<sign>[+-])?(?P<kind>longwake|wake_lock)=(?P<owner>[^:]+):\"AudioMix\""
)
# Wake lock u0a346 AudioMix: 56m 55s 468ms (0 times) max=3578572 actual=3578572 realtime
SUMMARY_RE = re.compile(
    r"^\s*Wake lock (?P<owner>\S+) AudioMix:\s+"
    r"(?P<duration>[\dhmsms .]+?)\s+\((?P<times>\d+) times\)\s+"
    r"max=(?P<max>\d+)\s+actual=(?P<actual>\d+)"
)
PKG_UID_RE = re.compile(
    r"(?P<pkg>[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)/(?P<uid>u0a\d+|\d+)"
)
A_UID_RE = re.compile(r"A=(?P<num>\d+):(?P<pkg>[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)")
PROC_RE = re.compile(
    r"ProcessRecord\{[^}]+\}\s+\d+:(?P<pkg>[a-zA-Z][a-zA-Z0-9_]*(?:\.[a-zA-Z0-9_]+)+)/(?P<uid>u0a\d+|\d+)"
)

KNOWN_OWNERS = {
    "1041": "audioserver",
    "1000": "system",
    "1001": "radio",
    "1013": "media",
    "1021": "gps",
    "1073": "network_stack",
}

# duration bucket labels (seconds)
DURATION_BUCKETS: List[Tuple[str, float, Optional[float]]] = [
    ("极长持锁(>=30分钟)", 1800, None),
    ("长持锁(5~30分钟)", 300, 1800),
    ("中等持锁(1~5分钟)", 60, 300),
    ("短持锁(10秒~1分钟)", 10, 60),
    ("极短持锁(<10秒)", 0, 10),
]


def _setup_utf8_stdio() -> None:
    import sys

    for name in ("stdin", "stdout", "stderr"):
        stream = getattr(sys, name, None)
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def _is_real_bugreport_txt(p: Path) -> bool:
    """排除 dumpstate_log / dumpstate-stats / 本流程产物 txt。"""
    name = p.name.lower()
    if not name.endswith(".txt") or "bugreport" not in name:
        return False
    if "dumpstate" in name:
        return False
    if name in {
        "bugreport_audiomix.txt",
        "bugreport_longwake.txt",
        "bugreport_audiomix_result.txt",
    }:
        return False
    if not p.is_file():
        return False
    try:
        return p.stat().st_size > 1024
    except OSError:
        return False


def find_bugreport_txt(path: Path) -> Path:
    path = path.resolve()
    if path.is_file():
        if _is_real_bugreport_txt(path):
            return path
        raise FileNotFoundError(f"不是 bugreport txt 文件: {path}")
    # 优先短路径主文件（UNC 长路径规避）
    main = path / "bugreport_main.txt"
    if _is_real_bugreport_txt(main):
        return main
    candidates = sorted(
        (p for p in path.glob("bugreport*.txt") if _is_real_bugreport_txt(p)),
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if not candidates:
        candidates = sorted(
            (p for p in path.rglob("bugreport*.txt") if _is_real_bugreport_txt(p)),
            key=lambda p: (1 if p.name.lower() == "bugreport_main.txt" else 0, p.stat().st_size),
            reverse=True,
        )
    if not candidates:
        raise FileNotFoundError(f"未找到 bugreport txt: {path}")
    return candidates[0]


def parse_timestamp(ts: str, year: int) -> datetime:
    return datetime.strptime(f"{year}-{ts}", "%Y-%m-%d %H:%M:%S.%f")


def infer_year(lines: Iterable[str]) -> int:
    for line in lines:
        m = TS_RE.search(line)
        if m:
            month = int(m.group(1)[:2])
            # bugreport 通常跨午夜；默认用采集日附近年份
            return datetime.now().year if month <= 12 else datetime.now().year
    return datetime.now().year


def owner_to_numeric(owner: str) -> Optional[int]:
    owner = owner.strip()
    if owner.startswith("u") and "a" in owner:
        try:
            app_id = int(owner.split("a", 1)[1])
            return 10000 + app_id
        except ValueError:
            return None
    if owner.isdigit():
        return int(owner)
    return None


def build_uid_map(text: str) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    for m in PKG_UID_RE.finditer(text):
        mapping.setdefault(m.group("uid"), m.group("pkg"))

    for m in A_UID_RE.finditer(text):
        uid_num = int(m.group("num"))
        uid_key = f"u0a{uid_num - 10000}" if uid_num >= 10000 else str(uid_num)
        mapping.setdefault(uid_key, m.group("pkg"))
        mapping.setdefault(str(uid_num), m.group("pkg"))

    for m in PROC_RE.finditer(text):
        mapping.setdefault(m.group("uid"), m.group("pkg"))

    # 系统 uid 强制使用固定名（1000=system，避免被 com.android.settings 等系统包覆盖）
    for owner, label in KNOWN_OWNERS.items():
        mapping[owner] = label

    return mapping


def resolve_owner_label(owner: str, uid_map: Dict[str, str]) -> str:
    pkg = uid_map.get(owner)
    if pkg:
        return f"{owner} ({pkg})"
    num = owner_to_numeric(owner)
    if num is not None:
        pkg2 = uid_map.get(str(num))
        if pkg2:
            return f"{owner} ({pkg2})"
    known = KNOWN_OWNERS.get(owner)
    if known:
        return f"{owner} ({known})"
    return owner


def parse_duration_ms(text: str) -> int:
    text = text.strip()
    total_ms = 0
    matched = False
    for part in re.finditer(r"(\d+)\s*([dhms]+)", text):
        val = int(part.group(1))
        unit = part.group(2)
        matched = True
        if unit == "h":
            total_ms += val * 3600_000
        elif unit == "m":
            total_ms += val * 60_000
        elif unit == "s":
            total_ms += val * 1000
        elif unit == "d":
            total_ms += val * 86400_000
        elif unit == "ms":
            total_ms += val
    if matched:
        return total_ms
    if text.isdigit():
        return int(text)
    return 0


def format_duration_ms(ms: int) -> str:
    if ms < 0:
        ms = 0
    if ms < 1000:
        return f"{ms}ms"
    sec = ms // 1000
    ms_rem = ms % 1000
    parts: List[str] = []
    h, sec = divmod(sec, 3600)
    m, sec = divmod(sec, 60)
    if h:
        parts.append(f"{h}h")
    if m:
        parts.append(f"{m}m")
    if sec or ms_rem:
        if ms_rem:
            parts.append(f"{sec}.{ms_rem:03d}s")
        else:
            parts.append(f"{sec}s")
    return " ".join(parts) if parts else "0ms"


def duration_bucket(sec: float) -> str:
    for label, low, high in DURATION_BUCKETS:
        if high is None and sec >= low:
            return label
        if high is not None and low <= sec < high:
            return label
    return "未知"


@dataclass
class TimelineEvent:
    line_no: int
    timestamp: str
    dt: str
    action: str  # acquire / release / held_at_start
    kind: str  # longwake / wake_lock
    owner: str
    owner_label: str
    raw: str
    scenes_at: List[dict] = field(default_factory=list)


@dataclass
class HoldInterval:
    owner: str
    owner_label: str
    kind: str
    start: str
    end: Optional[str]
    duration_ms: int
    duration_text: str
    bucket: str
    procstate: str = ""
    incomplete: bool = False
    unreliable: bool = False
    unreliable_reason: str = ""
    scenes: List[dict] = field(default_factory=list)
    abnormal: bool = False
    abnormal_reasons: List[str] = field(default_factory=list)
    abnormal_hold_ms: int = 0
    abnormal_hold_text: str = ""


@dataclass
class SummaryStat:
    owner: str
    owner_label: str
    duration_text: str
    duration_ms: int
    times: int
    max_ms: int
    actual_ms: int
    bucket: str


@dataclass
class AudioMixReport:
    bugreport_txt: str
    generated_at: str
    uid_map: Dict[str, str] = field(default_factory=dict)
    timeline_events: List[TimelineEvent] = field(default_factory=list)
    intervals: List[HoldInterval] = field(default_factory=list)
    summary_stats: List[SummaryStat] = field(default_factory=list)
    by_owner_totals: Dict[str, dict] = field(default_factory=dict)
    by_bucket: Dict[str, List[dict]] = field(default_factory=dict)
    scenes: List[dict] = field(default_factory=list)
    abnormal_intervals: List[dict] = field(default_factory=list)
    abnormal_count: int = 0


def parse_timeline_events(text: str, uid_map: Dict[str, str], year: int) -> List[TimelineEvent]:
    events: List[TimelineEvent] = []
    for line_no, line in enumerate(text.splitlines(), 1):
        if "AudioMix" not in line or ("longwake" not in line and "wake_lock" not in line):
            continue
        ts_m = TS_RE.search(line)
        if not ts_m:
            continue
        ts_str = ts_m.group(1)
        dt = parse_timestamp(ts_str, year).isoformat(sep=" ")
        raw = line.strip()
        for ev_m in EVENT_RE.finditer(line):
            sign = ev_m.group("sign") or ""
            kind = ev_m.group("kind")
            owner = ev_m.group("owner")
            if sign == "-":
                action = "release"
            elif sign == "+":
                action = "acquire"
            else:
                action = "held_at_start"
            events.append(
                (
                    ev_m.start(),
                    TimelineEvent(
                        line_no=line_no,
                        timestamp=ts_str,
                        dt=dt,
                        action=action,
                        kind=kind,
                        owner=owner,
                        owner_label=resolve_owner_label(owner, uid_map),
                        raw=raw,
                    ),
                )
            )
    events.sort(key=lambda item: (item[1].dt, item[1].line_no, item[0]))
    return [ev for _, ev in events]


def build_intervals(events: List[TimelineEvent]) -> List[HoldInterval]:
    """按 owner+kind 引用计数（LIFO）配对 + / -，支持同 owner 嵌套 acquire。"""
    open_stacks: Dict[Tuple[str, str], List[TimelineEvent]] = {}
    intervals: List[HoldInterval] = []

    for ev in events:
        key = (ev.owner, ev.kind)
        if ev.action in ("acquire", "held_at_start"):
            open_stacks.setdefault(key, []).append(ev)
            continue
        if ev.action == "release":
            stack = open_stacks.get(key)
            if not stack:
                continue
            start_ev = stack.pop()
            start_dt = datetime.fromisoformat(start_ev.dt)
            end_dt = datetime.fromisoformat(ev.dt)
            dur_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))
            procstate = ""
            pm = re.search(r"procstate:\s*(.+?)\s*$", ev.raw)
            if pm:
                procstate = pm.group(1)
            sec = dur_ms / 1000.0
            intervals.append(
                HoldInterval(
                    owner=ev.owner,
                    owner_label=ev.owner_label,
                    kind=ev.kind,
                    start=start_ev.timestamp,
                    end=ev.timestamp,
                    duration_ms=dur_ms,
                    duration_text=format_duration_ms(dur_ms),
                    bucket=duration_bucket(sec),
                    procstate=procstate,
                    incomplete=False,
                )
            )

    for (owner, kind), stack in sorted(open_stacks.items()):
        if not stack:
            continue
        start_ev = stack[0]
        intervals.append(
            HoldInterval(
                owner=owner,
                owner_label=start_ev.owner_label,
                kind=kind,
                start=start_ev.timestamp,
                end=None,
                duration_ms=-1,
                duration_text="未释放(至 bugreport 结束)",
                bucket="未闭合",
                incomplete=True,
            )
        )

    intervals.sort(key=lambda x: (x.start, x.owner))
    return intervals


def _battery_stats_budget_ms(summary_stats: List[SummaryStat]) -> Dict[str, int]:
    out: Dict[str, int] = {}
    for st in summary_stats:
        budget = st.actual_ms if st.actual_ms > 0 else st.duration_ms
        out[st.owner] = max(0, budget)
    return out


def _single_segment_unreliable_threshold_ms(budget_ms: int) -> int:
    """单段超过此阈值则视为 log 漏释锁产生的假长段；短段默认可信。"""
    if budget_ms <= 0:
        return 10_000
    return max(int(budget_ms * 2), budget_ms + 5000, 10_000)


def validate_intervals_against_battery_stats(
    intervals: List[HoldInterval],
    summary_stats: List[SummaryStat],
) -> None:
    """用 BatteryStats 交叉校验：仅标记明显超长的假段，短段保留可信。"""
    bs_budget = _battery_stats_budget_ms(summary_stats)
    by_owner: Dict[str, List[HoldInterval]] = {}
    for itv in intervals:
        if itv.incomplete:
            continue
        by_owner.setdefault(itv.owner, []).append(itv)

    for owner, itvs in by_owner.items():
        budget = bs_budget.get(owner)
        if budget is None:
            continue
        bs_text = next(
            (s.duration_text for s in summary_stats if s.owner == owner),
            format_duration_ms(budget),
        )
        threshold = _single_segment_unreliable_threshold_ms(budget)

        for itv in itvs:
            if itv.duration_ms >= threshold:
                itv.unreliable = True
                itv.unreliable_reason = (
                    f"单段 {itv.duration_text} 超过 BatteryStats 总量 {bs_text} "
                    f"（判定阈值 {format_duration_ms(threshold)}）；"
                    f"疑似 log 中 + 与 - 跨场景错配（漏释锁）"
                )


def parse_summary_stats(text: str, uid_map: Dict[str, str]) -> List[SummaryStat]:
    stats: List[SummaryStat] = []
    seen: set[str] = set()
    for line in text.splitlines():
        m = SUMMARY_RE.match(line)
        if not m:
            continue
        owner = m.group("owner")
        if owner in seen:
            continue
        seen.add(owner)
        dur_text = m.group("duration").strip()
        dur_ms = parse_duration_ms(dur_text)
        sec = dur_ms / 1000.0
        stats.append(
            SummaryStat(
                owner=owner,
                owner_label=resolve_owner_label(owner, uid_map),
                duration_text=dur_text,
                duration_ms=dur_ms,
                times=int(m.group("times")),
                max_ms=int(m.group("max")),
                actual_ms=int(m.group("actual")),
                bucket=duration_bucket(sec),
            )
        )
    stats.sort(key=lambda s: s.duration_ms, reverse=True)
    return stats


def aggregate_by_owner(intervals: List[HoldInterval], summary_stats: List[SummaryStat]) -> Dict[str, dict]:
    totals: Dict[str, dict] = {}
    for itv in intervals:
        if itv.incomplete:
            continue
        rec = totals.setdefault(
            itv.owner,
            {
                "owner": itv.owner,
                "owner_label": itv.owner_label,
                "interval_count": 0,
                "interval_count_unreliable": 0,
                "timeline_total_ms": 0,
                "timeline_trusted_ms": 0,
                "timeline_unreliable_ms": 0,
                "longwake_ms": 0,
                "wake_lock_ms": 0,
                "max_single_ms": 0,
                "max_trusted_ms": 0,
            },
        )
        rec["timeline_total_ms"] += itv.duration_ms
        if itv.unreliable:
            rec["interval_count_unreliable"] += 1
            rec["timeline_unreliable_ms"] += itv.duration_ms
        else:
            rec["interval_count"] += 1
            rec["timeline_trusted_ms"] += itv.duration_ms
            if itv.kind == "longwake":
                rec["longwake_ms"] += itv.duration_ms
            else:
                rec["wake_lock_ms"] += itv.duration_ms
            rec["max_trusted_ms"] = max(rec["max_trusted_ms"], itv.duration_ms)
        rec["max_single_ms"] = max(rec["max_single_ms"], itv.duration_ms)

    for st in summary_stats:
        rec = totals.setdefault(
            st.owner,
            {
                "owner": st.owner,
                "owner_label": st.owner_label,
                "interval_count": 0,
                "interval_count_unreliable": 0,
                "timeline_total_ms": 0,
                "timeline_trusted_ms": 0,
                "timeline_unreliable_ms": 0,
                "longwake_ms": 0,
                "wake_lock_ms": 0,
                "max_single_ms": 0,
                "max_trusted_ms": 0,
            },
        )
        rec["battery_stats_ms"] = st.duration_ms
        rec["battery_stats_actual_ms"] = st.actual_ms
        rec["battery_stats_text"] = st.duration_text
        rec["battery_stats_times"] = st.times

    for rec in totals.values():
        rec["timeline_total_text"] = format_duration_ms(rec.get("timeline_total_ms", 0))
        rec["timeline_trusted_text"] = format_duration_ms(rec.get("timeline_trusted_ms", 0))
        rec["timeline_unreliable_text"] = format_duration_ms(rec.get("timeline_unreliable_ms", 0))
        if rec.get("max_single_ms"):
            rec["max_single_text"] = format_duration_ms(rec["max_single_ms"])
        if rec.get("max_trusted_ms"):
            rec["max_trusted_text"] = format_duration_ms(rec["max_trusted_ms"])
        bs_ms = rec.get("battery_stats_actual_ms") or rec.get("battery_stats_ms") or 0
        trusted = rec.get("timeline_trusted_ms", 0)
        unreliable = rec.get("timeline_unreliable_ms", 0)
        rec["battery_stats_mismatch"] = bool(
            bs_ms > 0 and (unreliable > 0 or trusted > max(bs_ms * 2, bs_ms + 5000))
        )
        rec["display_timeline_text"] = (
            rec["timeline_trusted_text"]
            if rec.get("battery_stats_mismatch")
            else rec["timeline_total_text"]
        )
    return dict(
        sorted(
            totals.items(),
            key=lambda kv: kv[1].get("timeline_trusted_ms", kv[1].get("timeline_total_ms", 0)),
            reverse=True,
        )
    )


def bucket_intervals(intervals: List[HoldInterval]) -> Dict[str, List[dict]]:
    buckets: Dict[str, List[dict]] = {label: [] for label, _, _ in DURATION_BUCKETS}
    buckets["未闭合"] = []
    for itv in intervals:
        key = itv.bucket if itv.bucket in buckets else "未闭合"
        buckets.setdefault(key, []).append(asdict(itv))
    return {k: v for k, v in buckets.items() if v}


def analyze_bugreport(path: Path) -> AudioMixReport:
    txt_path = find_bugreport_txt(path)
    text = txt_path.read_text(encoding="utf-8", errors="replace")
    year = infer_year(text.splitlines())
    uid_map = build_uid_map(text)
    events = parse_timeline_events(text, uid_map, year)
    intervals = build_intervals(events)
    summary_stats = parse_summary_stats(text, uid_map)
    validate_intervals_against_battery_stats(intervals, summary_stats)
    by_owner = aggregate_by_owner(intervals, summary_stats)
    by_bucket = bucket_intervals(intervals)

    return AudioMixReport(
        bugreport_txt=str(txt_path),
        generated_at=datetime.now().isoformat(timespec="seconds"),
        uid_map=uid_map,
        timeline_events=events,
        intervals=intervals,
        summary_stats=summary_stats,
        by_owner_totals=by_owner,
        by_bucket=by_bucket,
    )


def short_app_name(owner_label: str, uid_map: Dict[str, str]) -> str:
    """短名：包名末段；末段过于泛化时取末两段。"""
    m = re.match(r"u0a\d+\s+\(([^)]+)\)|(\d+)\s+\(([^)]+)\)|(.+)", owner_label)
    pkg = ""
    if m:
        pkg = m.group(1) or m.group(3) or m.group(4) or ""
    if not pkg or "." not in pkg:
        return pkg or owner_label
    parts = pkg.split(".")
    generic_tail = {"music", "ad", "android", "apps", "id", "pro", "lite"}
    if parts[-1] in generic_tail and len(parts) >= 2:
        return ".".join(parts[-2:])
    return parts[-1]


def _ts_to_dt(ts: str, year: int) -> datetime:
    return parse_timestamp(ts, year)


def _report_year(report: AudioMixReport) -> int:
    if report.timeline_events:
        return int(report.timeline_events[0].dt[:4])
    return datetime.now().year


def _timeline_range(report: AudioMixReport) -> Tuple[Optional[datetime], Optional[datetime], int]:
    year = _report_year(report)
    dts: List[datetime] = []
    for ev in report.timeline_events:
        dts.append(_ts_to_dt(ev.timestamp, year))
    for itv in report.intervals:
        if itv.incomplete:
            continue
        dts.append(_ts_to_dt(itv.start, year))
        if itv.end:
            dts.append(_ts_to_dt(itv.end, year))
    if not dts:
        return None, None, year
    return min(dts), max(dts), year


BUCKET_COLORS = {
    "极长持锁(>=30分钟)": "#dc2626",
    "长持锁(5~30分钟)": "#ea580c",
    "中等持锁(1~5分钟)": "#ca8a04",
    "短持锁(10秒~1分钟)": "#16a34a",
    "极短持锁(<10秒)": "#6b7280",
    "未闭合": "#9333ea",
}


def _scene_label(sc: dict) -> str:
    desc = (sc.get("desc") or sc.get("name") or "").strip()
    suffix = sc.get("suffix") or ""
    screen = sc.get("screen_label") or ""
    if suffix and desc:
        return f"{desc}({suffix})[{screen}]"
    return desc or sc.get("name") or "?"


def format_timeline_visual(report: AudioMixReport) -> str:
    """按时间顺序的可视化时间轴（TXT）。"""
    lines: List[str] = []
    year = _report_year(report)
    t_min, t_max, _ = _timeline_range(report)
    if t_min and t_max:
        span = t_max - t_min
        lines.append(
            f"时间范围: {t_min.strftime('%m-%d %H:%M:%S')} ~ "
            f"{t_max.strftime('%m-%d %H:%M:%S')} "
            f"(跨度 {format_duration_ms(int(span.total_seconds() * 1000))})"
        )
    lines.append("")
    lines.append("图例: ▶持锁开始  ■持锁结束  ○日志起点已持锁  ──持锁区间条  ⚠场景内异常持锁  ~不可靠(与BatteryStats不符)")
    lines.append("")

    if report.scenes:
        lines.append(f"【DOU 场景窗口】共 {len(report.scenes)} 个")
        for sc in report.scenes:
            lines.append(f"  {sc['start']} ~ {sc['end']} | {_scene_label(sc)} | {sc.get('category', '')}")
        lines.append("")

    # 区间索引：release 事件 -> 对应区间
    release_map: Dict[str, HoldInterval] = {}
    for itv in report.intervals:
        if itv.end and not itv.incomplete:
            release_map[f"{itv.end}|{itv.owner}|{itv.kind}"] = itv

    open_holds: Dict[Tuple[str, str], TimelineEvent] = {}
    action_sym = {"acquire": "▶", "release": "■", "held_at_start": "○"}
    action_cn = {"acquire": "持锁+", "release": "释锁-", "held_at_start": "已持锁"}

    for ev in report.timeline_events:
        sym = action_sym.get(ev.action, "·")
        app = short_app_name(ev.owner_label, report.uid_map)
        ts = ev.timestamp
        head = f"{ts}  {sym} [{action_cn.get(ev.action, ev.action):^4}] {ev.kind:9} {app}"
        if ev.scenes_at:
            scene_txt = " | ".join(_scene_label(s) for s in ev.scenes_at[:2])
            if len(ev.scenes_at) > 2:
                scene_txt += f" +{len(ev.scenes_at) - 2}"
            head += f"  @ {scene_txt}"

        if ev.action in ("acquire", "held_at_start"):
            key = (ev.owner, ev.kind)
            if key not in open_holds:
                open_holds[key] = ev
            parallel = sum(1 for _ in open_holds) - 1
            if parallel > 0:
                head += f"  (当前并行持锁 {len(open_holds)} 路)"
            lines.append(head)
            continue

        if ev.action == "release":
            key = (ev.owner, ev.kind)
            start_ev = open_holds.pop(key, None)
            itv = release_map.get(f"{ev.timestamp}|{ev.owner}|{ev.kind}")
            if itv:
                bar_len = min(40, max(4, itv.duration_ms // 15000))
                bar = "━" * bar_len
                ps = f" | {itv.procstate}" if itv.procstate else ""
                ab = ""
                if itv.unreliable:
                    ab = f" ~不可靠({itv.unreliable_reason})"
                elif itv.abnormal:
                    ab = " ⚠异常"
                    if itv.abnormal_reasons:
                        ab += f" ({itv.abnormal_reasons[0]})"
                scene_part = ""
                if itv.scenes:
                    scene_part = " @ " + " | ".join(_scene_label(s) for s in itv.scenes[:2])
                lines.append(
                    f"{head}{scene_part}  │ {bar} {itv.duration_text} │ [{itv.bucket}]{ps}{ab}"
                )
            elif start_ev:
                start_dt = _ts_to_dt(start_ev.timestamp, year)
                end_dt = _ts_to_dt(ev.timestamp, year)
                dur_ms = max(0, int((end_dt - start_dt).total_seconds() * 1000))
                lines.append(f"{head}  │ {format_duration_ms(dur_ms)} │")
            else:
                lines.append(f"{head}  (无配对开始事件)")
            continue

        lines.append(head)

    lines.append("")
    lines.append("【持锁区间条带图】(按开始时间排序，宽度∝时长)")
    lines.append("")
    complete = [i for i in report.intervals if not i.incomplete]
    complete.sort(key=lambda x: x.start)
    if not complete:
        lines.append("  (无完整区间)")
        return "\n".join(lines)

    max_ms = max(i.duration_ms for i in complete) or 1
    for itv in complete:
        app = short_app_name(itv.owner_label, report.uid_map)
        bar_len = max(2, int(itv.duration_ms / max_ms * 36))
        bar = "░" * bar_len if itv.unreliable else "█" * bar_len
        end = itv.end or "?"
        flag = ""
        if itv.unreliable:
            flag = " ~"
        elif itv.abnormal:
            flag = " ⚠"
        lines.append(
            f"  {itv.start} ─{bar}─ {end}  "
            f"{itv.duration_text:>12}  {app}  [{itv.bucket}]"
            f"{flag}"
        )
    if report.abnormal_intervals:
        lines.append("")
        lines.append(f"【场景内异常持锁】{len(report.abnormal_intervals)} 段")
        for ab in report.abnormal_intervals:
            sc = ab.get("scenes") or []
            sc_txt = " | ".join(_scene_label(s) for s in sc if s.get("abnormal")) or "-"
            lines.append(
                f"  ⚠ {ab.get('start')} ~ {ab.get('end')} | {ab.get('owner_label')} | "
                f"持锁 {ab.get('duration_text')} | 异常持锁 {ab.get('overlap_text') or ab.get('abnormal_hold_text') or '-'} | "
                f"阈值 {ab.get('threshold_text') or '-'} | 场景: {sc_txt} | "
                f"{'; '.join(ab.get('reasons') or [])}"
            )
    return "\n".join(lines)


def format_html_report(report: AudioMixReport) -> str:
    """HTML 时间轴页面。"""
    year = _report_year(report)
    t_min, t_max, _ = _timeline_range(report)
    if not t_min or not t_max:
        return "<html><body><p>无 AudioMix 时间轴数据</p></body></html>"

    span_ms = max(1, int((t_max - t_min).total_seconds() * 1000))
    t_min_s = t_min.strftime("%m-%d %H:%M:%S")
    t_max_s = t_max.strftime("%m-%d %H:%M:%S")

    def pct(ts: str) -> float:
        dt = _ts_to_dt(ts, year)
        return max(0.0, min(100.0, (dt - t_min).total_seconds() * 1000 / span_ms * 100))

    # 按 owner 分泳道
    lanes: Dict[str, List[HoldInterval]] = {}
    for itv in report.intervals:
        if itv.incomplete:
            continue
        lanes.setdefault(itv.owner_label, []).append(itv)

    lane_html: List[str] = []
    for owner_label, items in sorted(
        lanes.items(), key=lambda kv: sum(i.duration_ms for i in kv[1]), reverse=True
    ):
        app = short_app_name(owner_label, report.uid_map)
        bars: List[str] = []
        trusted_items = [i for i in items if not i.unreliable]
        total_ms = sum(i.duration_ms for i in trusted_items)
        if not total_ms:
            total_ms = sum(i.duration_ms for i in items)
        total_text = format_duration_ms(total_ms)
        ab_total_ms = sum(
            getattr(i, "abnormal_hold_ms", 0) or 0
            for i in items
            if i.abnormal and not i.unreliable
        )
        ab_total_text = format_duration_ms(ab_total_ms) if ab_total_ms > 0 else ""
        for itv in sorted(items, key=lambda x: x.start):
            left = pct(itv.start)
            end_ts = itv.end or t_max_s
            width = max(0.3, pct(end_ts) - left)
            color = BUCKET_COLORS.get(itv.bucket, "#64748b")
            bar_label = ""
            css_cls = "bar"
            if itv.unreliable:
                color = "#64748b"
                css_cls = "bar unreliable"
                bar_label = '<span class="bar-label">~不可靠</span>'
            elif itv.abnormal:
                color = "#dc2626"
                css_cls = "bar abnormal"
                ab_hold = getattr(itv, "abnormal_hold_text", "") or itv.duration_text
                bar_label = f'<span class="bar-label">异常{ab_hold}</span>'
            title = (
                f"{itv.start} ~ {itv.end or '未释放'}\\n"
                f"{itv.duration_text} [{itv.bucket}]\\n{owner_label}"
            )
            if itv.unreliable:
                title += f"\\n~ {itv.unreliable_reason}"
            if itv.abnormal and getattr(itv, "abnormal_hold_text", ""):
                title += f"\\n异常持锁 {itv.abnormal_hold_text}"
            if itv.scenes:
                title += "\\n场景: " + " | ".join(_scene_label(s) for s in itv.scenes[:3])
            if itv.abnormal_reasons:
                title += "\\n⚠ " + "; ".join(itv.abnormal_reasons)
            bars.append(
                f'<div class="{css_cls}" style="left:{left:.2f}%;width:{width:.2f}%;'
                f'background:{color}" title="{title}">{bar_label}</div>'
            )
        ab_line = (
            f'<span class="lane-abnormal">⚠ {ab_total_text}</span>'
            if ab_total_text
            else ""
        )
        ab_col = (
            f'<div class="lane-abnormal-col">{ab_total_text}</div>'
            if ab_total_text
            else '<div class="lane-abnormal-col empty">—</div>'
        )
        lane_html.append(
            f'<div class="lane"><div class="lane-label" title="{owner_label}">'
            f'{app}<span class="lane-total">Σ {total_text}</span>{ab_line}</div>'
            f'<div class="lane-track">{"".join(bars)}</div>'
            f'<div class="lane-total-col">{total_text}</div>{ab_col}</div>'
        )

    # 事件点
    event_marks: List[str] = []
    action_color = {"acquire": "#22c55e", "release": "#ef4444", "held_at_start": "#3b82f6"}
    for ev in report.timeline_events:
        left = pct(ev.timestamp)
        color = action_color.get(ev.action, "#94a3b8")
        app = short_app_name(ev.owner_label, report.uid_map)
        sym = {"acquire": "+", "release": "-", "held_at_start": "○"}.get(ev.action, "·")
        event_marks.append(
            f'<div class="evt" style="left:{left:.2f}%;color:{color}" '
            f'title="{ev.timestamp} {ev.action} {ev.owner_label}">{sym}</div>'
        )

    # 刻度
    ticks: List[str] = []
    tick_count = 8
    for i in range(tick_count + 1):
        p = i / tick_count * 100
        tick_dt = t_min + (t_max - t_min) * i / tick_count
        ticks.append(
            f'<span class="tick" style="left:{p:.1f}%">{tick_dt.strftime("%m-%d %H:%M")}</span>'
        )

    # DOU 场景背景带
    scene_bands: List[str] = []
    scene_colors = {"亮屏": "rgba(59,130,246,0.12)", "灭屏": "rgba(100,116,139,0.18)"}
    for sc in report.scenes:
        left = pct(sc["start"])
        width = max(0.3, pct(sc["end"]) - left)
        bg = scene_colors.get(sc.get("screen_label"), "rgba(148,163,184,0.1)")
        label = _scene_label(sc).replace('"', "'")
        scene_bands.append(
            f'<div class="scene-band" style="left:{left:.2f}%;width:{width:.2f}%;background:{bg}" '
            f'title="{label}"></div>'
        )

    abnormal_rows = ""
    for ab in report.abnormal_intervals:
        sc_txt = " | ".join(
            _scene_label(s) for s in (ab.get("scenes") or []) if s.get("abnormal")
        )
        abnormal_rows += (
            f"<tr class='abnormal-row'><td>{ab.get('start')}</td><td>{ab.get('end')}</td>"
            f"<td>{ab.get('owner_label')}</td><td>{ab.get('duration_text')}</td>"
            f"<td>{ab.get('overlap_text') or ab.get('abnormal_hold_text') or '-'}</td>"
            f"<td>{ab.get('threshold_text') or '-'}</td>"
            f"<td>{sc_txt}</td><td>{'; '.join(ab.get('reasons') or [])}</td></tr>"
        )

    scene_lane_html = ""
    if scene_bands:
        scene_lane_html = f"""
<div class="panel">
<h2>DOU 场景窗口</h2>
<div class="axis-wrap">{"".join(ticks)}</div>
<div class="scene-row"><div class="lane-label">场景</div><div class="lane-track scene-track">{"".join(scene_bands)}</div></div>
</div>"""

    abnormal_panel = ""
    if abnormal_rows:
        abnormal_panel = f"""
<div class="panel abnormal-panel">
<h2>⚠ 场景内异常 AudioMix 持锁 ({report.abnormal_count})</h2>
<table><thead><tr><th>开始</th><th>结束</th><th>持锁方</th><th>持锁时长</th><th>异常持锁时间</th><th>阈值</th><th>重叠场景</th><th>原因</th></tr></thead>
<tbody>{abnormal_rows}</tbody></table>
</div>"""

    summary_rows = ""
    for st in report.summary_stats:
        color = BUCKET_COLORS.get(st.bucket, "#64748b")
        summary_rows += (
            f'<tr><td>{st.owner_label}</td><td>{st.duration_text}</td>'
            f'<td>{st.times}</td><td><span class="badge" style="background:{color}">'
            f'{st.bucket}</span></td></tr>'
        )

    event_rows = ""
    action_cn = {"acquire": "持锁+", "release": "释锁-", "held_at_start": "已持锁"}
    release_map = {
        f"{i.end}|{i.owner}|{i.kind}": i
        for i in report.intervals
        if i.end and not i.incomplete
    }
    for ev in report.timeline_events:
        dur = ""
        if ev.action == "release":
            itv = release_map.get(f"{ev.timestamp}|{ev.owner}|{ev.kind}")
            if itv:
                dur = itv.duration_text
        scene_txt = ""
        if ev.scenes_at:
            scene_txt = " | ".join(_scene_label(s) for s in ev.scenes_at[:2])
        event_rows += (
            f"<tr><td>{ev.timestamp}</td><td>{action_cn.get(ev.action, ev.action)}</td>"
            f"<td>{ev.kind}</td><td>{ev.owner_label}</td><td>{dur}</td><td>{scene_txt}</td></tr>"
        )

    legend = "".join(
        f'<span class="legend-item"><i style="background:{c}"></i>{label}</span>'
        for label, c in BUCKET_COLORS.items()
        if label != "未闭合"
    )

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"/>
<title>AudioMix 持锁时间轴</title>
<style>
* {{ box-sizing: border-box; }}
body {{ font-family: "Segoe UI", system-ui, sans-serif; margin: 20px; background: #0f172a; color: #e2e8f0; }}
h1,h2 {{ color: #f8fafc; }}
.meta {{ color: #94a3b8; font-size: 13px; margin-bottom: 20px; }}
.panel {{ background: #1e293b; border-radius: 10px; padding: 16px 20px; margin-bottom: 20px; }}
.axis-wrap {{ position: relative; height: 24px; margin: 8px 0 28px 120px; border-bottom: 1px solid #475569; }}
.tick {{ position: absolute; transform: translateX(-50%); font-size: 10px; color: #94a3b8; top: 4px; white-space: nowrap; }}
.lane {{ display: flex; align-items: center; margin: 6px 0; }}
.lane-label {{ width: 120px; font-size: 12px; line-height: 1.25; overflow: hidden; color: #cbd5e1; flex-shrink: 0; text-align: right; padding-right: 8px; }}
.lane-label .lane-total {{ display: block; color: #2dd4bf; font-weight: 700; font-size: 11px; margin-top: 2px; }}
.lane-label .lane-abnormal {{ display: block; color: #fca5a5; font-weight: 700; font-size: 11px; margin-top: 2px; }}
.lane-total-col {{ width: 64px; flex-shrink: 0; font-size: 12px; font-weight: 700; color: #2dd4bf; padding-left: 4px; }}
.lane-abnormal-col {{ width: 72px; flex-shrink: 0; font-size: 12px; font-weight: 700; color: #fca5a5; padding-left: 4px; }}
.lane-abnormal-col.empty {{ color: #64748b; font-weight: 500; }}
.bar.abnormal {{ outline: 1px solid #fecaca; }}
.bar.unreliable {{ opacity: 0.45; border: 1px dashed #94a3b8; background: repeating-linear-gradient(45deg, #475569, #475569 4px, #64748b 4px, #64748b 8px) !important; }}
.bar-label {{ position: absolute; left: 2px; right: 2px; bottom: 0; font-size: 9px; color: #fff; font-weight: 700; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; text-shadow: 0 1px 1px rgba(0,0,0,0.45); pointer-events: none; }}
.lane-track {{ flex: 1; position: relative; height: 22px; background: #334155; border-radius: 4px; }}
.bar {{ position: absolute; top: 3px; height: 16px; border-radius: 3px; opacity: 0.92; cursor: pointer; min-width: 2px; }}
.bar:hover {{ opacity: 1; outline: 1px solid #fff; }}
.evt-row {{ position: relative; height: 18px; margin: 4px 0 12px 120px; }}
.evt {{ position: absolute; transform: translateX(-50%); font-size: 11px; font-weight: bold; cursor: default; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 12px; margin: 10px 0; font-size: 12px; }}
.legend-item i {{ display: inline-block; width: 12px; height: 12px; border-radius: 2px; margin-right: 4px; vertical-align: middle; }}
table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
th, td {{ border-bottom: 1px solid #334155; padding: 6px 8px; text-align: left; }}
th {{ color: #94a3b8; font-weight: 600; }}
.badge {{ display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; color: #fff; }}
.scene-row {{ display: flex; align-items: stretch; margin: 6px 0 16px; }}
.scene-track {{ min-height: 28px; }}
.scene-band {{ position: absolute; top: 0; bottom: 0; border-left: 1px solid rgba(255,255,255,0.15); }}
.abnormal-panel h2 {{ color: #fca5a5; }}
.abnormal-row td {{ color: #fecaca; }}
</style>
</head>
<body>
<h1>Bugreport AudioMix 持锁时间轴</h1>
<div class="meta">源: {report.bugreport_txt}<br/>范围: {t_min_s} ~ {t_max_s}（跨度 {format_duration_ms(span_ms)}）| 场景 {len(report.scenes)} | 异常 {report.abnormal_count}</div>

{scene_lane_html}

{abnormal_panel}

<div class="panel">
<h2>持锁区间（泳道图）</h2>
<div class="legend">{legend}</div>
<div class="axis-wrap">{"".join(ticks)}</div>
{"".join(lane_html)}
</div>

<div class="panel">
<h2>事件标记（+持锁 / -释锁 / ○已持锁）</h2>
<div class="evt-row">{"".join(event_marks)}</div>
<div class="axis-wrap">{"".join(ticks)}</div>
</div>

<div class="panel">
<h2>Battery Stats 汇总</h2>
<table><thead><tr><th>持锁方</th><th>累计</th><th>次数</th><th>分桶</th></tr></thead>
<tbody>{summary_rows}</tbody></table>
</div>

<div class="panel">
<h2>完整事件时间轴</h2>
<table><thead><tr><th>时间</th><th>动作</th><th>类型</th><th>持锁方</th><th>区间时长</th><th>当时场景</th></tr></thead>
<tbody>{event_rows}</tbody></table>
</div>
</body>
</html>"""


def format_text_report(report: AudioMixReport) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("Bugreport AudioMix 持锁分析")
    lines.append("=" * 72)
    lines.append(f"源文件: {report.bugreport_txt}")
    lines.append(f"生成时间: {report.generated_at}")
    lines.append("")

    lines.append("=" * 72)
    lines.append("【主视图】AudioMix 持锁时间轴")
    lines.append("=" * 72)
    lines.append(format_timeline_visual(report))
    lines.append("")

    lines.append("【Battery Stats 汇总（Wake lock AudioMix）】")
    if report.summary_stats:
        for st in report.summary_stats:
            lines.append(
                f"  - {st.owner_label}: 累计 {st.duration_text} "
                f"({st.times} 次, max={format_duration_ms(st.max_ms)}, "
                f"actual={format_duration_ms(st.actual_ms)}) [{st.bucket}]"
            )
    else:
        lines.append("  (未找到汇总行)")
    lines.append("")

    lines.append("【按持锁方累计（由时间轴区间汇总）】")
    if report.by_owner_totals:
        for rec in report.by_owner_totals.values():
            line = (
                f"  - {rec['owner_label']}: "
                f"可信区间 {rec['interval_count']} 段, "
                f"可信合计 {rec.get('timeline_trusted_text', '0ms')}, "
                f"最长可信单段 {rec.get('max_trusted_text', '0ms')}"
            )
            if rec.get("interval_count_unreliable"):
                line += (
                    f" | 不可靠 {rec['interval_count_unreliable']} 段 "
                    f"({rec.get('timeline_unreliable_text', '0ms')})"
                )
            if "battery_stats_text" in rec:
                line += f" | BatteryStats {rec['battery_stats_text']}"
            if rec.get("battery_stats_mismatch"):
                line += " ⚠ 与 BatteryStats 不符，优先看可信合计"
            lines.append(line)
    else:
        lines.append("  (无完整区间)")
    lines.append("")

    lines.append("【按时长分桶明细】")
    for label, _, _ in DURATION_BUCKETS:
        items = report.by_bucket.get(label, [])
        lines.append(f"  {label}: {len(items)} 段")
        for itv in items:
            end = itv.get("end") or "未释放"
            ps = f" procstate={itv['procstate']}" if itv.get("procstate") else ""
            flag = ""
            if itv.get("unreliable"):
                flag = f" ~不可靠: {itv.get('unreliable_reason', '')}"
            lines.append(
                f"    {itv['start']} ~ {end} | {itv['owner_label']} | "
                f"{itv['kind']} | {itv['duration_text']}{ps}{flag}"
            )
    if report.by_bucket.get("未闭合"):
        lines.append(f"  未闭合: {len(report.by_bucket['未闭合'])} 段")
        for itv in report.by_bucket["未闭合"]:
            lines.append(
                f"    {itv['start']} ~ 未释放 | {itv['owner_label']} | {itv['kind']}"
            )
    lines.append("")
    return "\n".join(lines)


def report_to_json(report: AudioMixReport) -> dict:
    return {
        "bugreport_txt": report.bugreport_txt,
        "generated_at": report.generated_at,
        "uid_map": report.uid_map,
        "summary_stats": [asdict(s) for s in report.summary_stats],
        "by_owner_totals": report.by_owner_totals,
        "by_bucket": report.by_bucket,
        "intervals": [asdict(i) for i in report.intervals],
        "timeline_events": [asdict(e) for e in report.timeline_events],
        "scenes": report.scenes,
        "abnormal_intervals": report.abnormal_intervals,
        "abnormal_count": report.abnormal_count,
    }


def _dou_unzip_module():
    scripts = Path(__file__).resolve().parent.parent.parent / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    from dou_unzip import ensure_bugreport_extracted  # noqa: WPS433

    return ensure_bugreport_extracted


def _read_low_from_meta_json(high_abs: str) -> str:
    """从 high 根目录元数据 JSON 解析 low 路径。

    优先级：``dou_prepare_result.json`` → ``scene_compare_result.json`` →
    ``power_analysis_result.json``。手工给 high/low 跑场景对比时通常只有
    ``scene_compare_result.json``，若只认 prepare 会导致第 9 步只跑 high。
    """
    for name in (
        "dou_prepare_result.json",
        "scene_compare_result.json",
        "power_analysis_result.json",
    ):
        path = Path(high_abs) / name
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        low_abs = str(data.get("low") or "").strip()
        if low_abs:
            return low_abs
    return ""


def resolve_dou_side_dirs(high: str, low: str = "") -> List[Tuple[str, str]]:
    """返回待跑 wakelock 的 (目录, side) 列表；side 为 high/low。

    low 解析顺序：``--low`` 显式参数 → high 根下 prepare/scene_compare/power_analysis JSON。
    解析不到 low 时**只跑 high**（并应由调用方按文档显式传 ``--low``）。
    """
    high_abs = os.path.abspath(str(high).strip())
    roots: List[Tuple[str, str]] = [(high_abs, "high")]
    low_abs = str(low or "").strip() or _read_low_from_meta_json(high_abs)
    if low_abs:
        low_abs = os.path.abspath(low_abs)
        if os.path.isdir(low_abs) and os.path.normcase(low_abs) != os.path.normcase(high_abs):
            roots.append((low_abs, "low"))
        else:
            print(
                f"WARN: 低功耗路径无效或与 high 相同，跳过 low wakelock：{low_abs}",
                file=sys.stderr,
            )
    else:
        print(
            "WARN: 未解析到低功耗目录（无 --low，且 high 下无 prepare/scene_compare/power_analysis 的 low）；"
            "本次只跑高功耗 wakelock。请显式：python .../run_bugreport_longwake.py <high> --low <low>",
            file=sys.stderr,
        )
    return roots


def find_bugreport_dir(root: Path) -> Optional[Path]:
    """在项目目录下查找 bugreport 解压目录（优先 phone_logs，取最大 txt）。"""
    root = root.resolve()
    if not root.is_dir():
        return None
    _dou_unzip_module()(root)

    def _priority(txt: Path) -> Tuple[int, int]:
        rel = txt.relative_to(root).as_posix().lower()
        pri = 0
        if txt.name.lower() == "bugreport_main.txt":
            pri = 4
        elif rel.startswith("phone_logs/") or "/phone_logs/" in rel:
            pri = 3
        elif "/bugreports/" in rel:
            pri = 2
        elif rel.startswith("meta_report/"):
            pri = 1
        try:
            size = txt.stat().st_size
        except OSError:
            size = 0
        return (pri, size)

    best_txt: Optional[Path] = None
    best_score: Tuple[int, int] = (-1, -1)
    for txt in root.rglob("bugreport*.txt"):
        if not _is_real_bugreport_txt(txt):
            continue
        score = _priority(txt)
        if score > best_score:
            best_score = score
            best_txt = txt
    return best_txt.parent if best_txt else None


def build_dou_result(
    report: AudioMixReport,
    high: str,
    bugreport_dir: Path,
    artifacts: dict,
    *,
    side: str = "high",
) -> dict:
    """DOU 流程落盘用精简结果（项目根目录 JSON）。"""
    top_owners = []
    for rec in list(report.by_owner_totals.values())[:8]:
        top_owners.append(
            {
                "owner_label": rec.get("owner_label"),
                "interval_count": rec.get("interval_count", 0),
                "interval_count_unreliable": rec.get("interval_count_unreliable", 0),
                "timeline_total_text": rec.get("timeline_total_text", "0ms"),
                "timeline_trusted_text": rec.get("timeline_trusted_text", "0ms"),
                "display_timeline_text": rec.get("display_timeline_text", "0ms"),
                "max_single_text": rec.get("max_single_text", "0ms"),
                "max_trusted_text": rec.get("max_trusted_text", "0ms"),
                "battery_stats_text": rec.get("battery_stats_text"),
                "battery_stats_mismatch": rec.get("battery_stats_mismatch", False),
            }
        )
    long_holds = []
    for label in ("极长持锁(>=30分钟)", "长持锁(5~30分钟)"):
        for itv in report.by_bucket.get(label, []):
            if itv.get("unreliable"):
                continue
            long_holds.append(
                {
                    "start": itv.get("start"),
                    "end": itv.get("end"),
                    "owner_label": itv.get("owner_label"),
                    "duration_text": itv.get("duration_text"),
                    "bucket": label,
                }
            )
    return {
        "high": high,
        "side": side,
        "skill": "flow_power_bugreport_audiomix",
        "step": "dou_2_bugreport_audiomix",
        "generated_at": report.generated_at,
        "bugreport_txt": report.bugreport_txt,
        "bugreport_dir": str(bugreport_dir),
        "artifacts": artifacts,
        "event_count": len(report.timeline_events),
        "interval_count": sum(1 for i in report.intervals if not i.incomplete),
        "interval_count_trusted": sum(
            1 for i in report.intervals if not i.incomplete and not i.unreliable
        ),
        "interval_count_unreliable": sum(
            1 for i in report.intervals if not i.incomplete and i.unreliable
        ),
        "scene_count": len(report.scenes),
        "abnormal_count": report.abnormal_count,
        "summary_stats": [asdict(s) for s in report.summary_stats[:8]],
        "top_owners": top_owners,
        "long_holds": long_holds,
        "scenes": report.scenes,
        "abnormal_intervals": report.abnormal_intervals,
        "annotated_intervals": [
            {
                **asdict(i),
                "scenes": i.scenes,
                "abnormal": i.abnormal,
                "abnormal_reasons": i.abnormal_reasons,
                "abnormal_hold_ms": getattr(i, "abnormal_hold_ms", 0),
                "abnormal_hold_text": getattr(i, "abnormal_hold_text", ""),
            }
            for i in report.intervals
            if not i.incomplete
        ],
        "timeline_events": [
            {
                **asdict(e),
                "scenes_at": e.scenes_at,
            }
            for e in report.timeline_events
        ],
        "has_audiomix_activity": bool(report.timeline_events or report.summary_stats),
    }


def format_dou_summary_text(result: dict) -> str:
    lines: List[str] = []
    lines.append("=" * 72)
    lines.append("DOU Bugreport AudioMix 持锁结论")
    lines.append("=" * 72)
    lines.append(f"高功耗目录: {result.get('high')}")
    lines.append(f"bugreport: {result.get('bugreport_txt')}")
    lines.append(
        f"事件 {result.get('event_count', 0)} | "
        f"完整区间 {result.get('interval_count', 0)} "
        f"(可信 {result.get('interval_count_trusted', 0)}, "
        f"不可靠 {result.get('interval_count_unreliable', 0)})"
    )
    lines.append("")
    lines.append("【Battery Stats Top】")
    for st in result.get("summary_stats") or []:
        lines.append(
            f"  - {st.get('owner_label')}: {st.get('duration_text')} [{st.get('bucket')}]"
        )
    lines.append("")
    lines.append("【时间轴持锁方 Top】")
    for rec in result.get("top_owners") or []:
        line = (
            f"  - {rec.get('owner_label')}: "
            f"{rec.get('interval_count', 0)} 段可信, "
            f"合计 {rec.get('display_timeline_text') or rec.get('timeline_trusted_text')}, "
            f"最长 {rec.get('max_trusted_text') or rec.get('max_single_text')}"
        )
        if rec.get("interval_count_unreliable"):
            line += f" (+{rec['interval_count_unreliable']} 段不可靠)"
        if rec.get("battery_stats_text"):
            line += f" | BatteryStats {rec['battery_stats_text']}"
        lines.append(line)
    lines.append("")
    lines.append("【极长/长持锁区间】")
    long_holds = result.get("long_holds") or []
    if long_holds:
        for itv in long_holds:
            lines.append(
                f"  - {itv.get('start')} ~ {itv.get('end')} | "
                f"{itv.get('owner_label')} | {itv.get('duration_text')} [{itv.get('bucket')}]"
            )
    else:
        lines.append("  (无 >=5min 区间)")
    lines.append("")
    lines.append("【场景内异常持锁】")
    ab_list = result.get("abnormal_intervals") or []
    if ab_list:
        for ab in ab_list:
            sc_txt = ", ".join(
                (s.get("desc") or s.get("name") or "")
                for s in (ab.get("scenes") or [])
                if s.get("abnormal")
            )
            lines.append(
                f"  ⚠ {ab.get('start')} ~ {ab.get('end')} | {ab.get('owner_label')} | "
                f"{ab.get('duration_text')} | 场景: {sc_txt or '-'} | "
                f"{'; '.join(ab.get('reasons') or [])}"
            )
    else:
        lines.append("  (未检出场景内异常 longwake)")
    arts = result.get("artifacts") or {}
    lines.append("")
    lines.append("【详细时间轴产物】")
    for key in ("txt", "html", "json"):
        if arts.get(key):
            lines.append(f"  - {key}: {arts[key]}")
    lines.append("")
    return "\n".join(lines)
